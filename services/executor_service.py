# services/executor_service.py
import asyncio
import os
import shlex
from typing import Dict, Any, Callable, Awaitable, Optional
from dataclasses import dataclass
from jinja2 import Template

# ── 레지스트리 ─────────────────────────────────────────────────
_HANDLER_REGISTRY: Dict[str, "ActionHandler"] = {}

def register(function_key: str):
    def deco(cls):
        _HANDLER_REGISTRY[function_key] = cls()
        return cls
    return deco

# ── 공통 결과 타입 ─────────────────────────────────────────────
@dataclass
class ExecResult:
    ok: bool
    message: str
    shortcut: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

# ── 베이스 핸들러 ─────────────────────────────────────────────
class ActionHandler:
    async def execute(self, params: Dict[str, Any]) -> ExecResult:
        raise NotImplementedError

    async def simulate(self, params: Dict[str, Any]) -> ExecResult:
        # 시뮬레이션 기본 구현
        return ExecResult(ok=True, message=f"[SIMULATION] Would execute with {params}")

    async def guide(self, params: Dict[str, Any]) -> ExecResult:
        # 가이드 기본 구현
        return ExecResult(ok=True, message="이 작업은 실행 모드에서만 수행됩니다.")

# ── 스크립트형(데이터 드리븐) 공통 핸들러 ─────────────────────
class GenericScriptHandler(ActionHandler):
    """
    DB의 functions 테이블에서 script_path/script_command/shortcut를 읽어
    템플릿으로 인자 바인딩 후 실행.
    """
    def __init__(self, script_path: str, script_command: str, shortcut: Optional[str] = None, shell: str = "powershell"):
        self.script_path = script_path
        self.script_command = script_command
        self.shortcut = shortcut
        self.shell = shell  # "powershell" | "cmd" | "sh"

    def _render_command(self, params: Dict[str, Any]) -> str:
        # Jinja 템플릿으로 안전 바인딩 (공백/따옴표는 쉘에서 처리)
        return Template(self.script_command).render(**(params or {}), SCRIPT_PATH=self.script_path)

    async def execute(self, params: Dict[str, Any]) -> ExecResult:
        cmd = self._render_command(params)

        if self.shell == "powershell":
            argv = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd]
        elif self.shell == "cmd":
            argv = ["cmd", "/c", cmd]
        else:  # POSIX
            argv = ["sh", "-c", cmd]

        proc = await asyncio.create_subprocess_exec(
            *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        out, err = await proc.communicate()
        if proc.returncode == 0:
            return ExecResult(ok=True, message=out.decode("utf-8", "ignore").strip(), shortcut=self.shortcut)
        return ExecResult(ok=False, message=err.decode("utf-8", "ignore").strip(), shortcut=self.shortcut)

# ── 파이썬 구현형 핸들러들(예: 파일 작업) ─────────────────────
@register("copy_file")
class CopyFileHandler(ActionHandler):
    async def execute(self, params: Dict[str, Any]) -> ExecResult:
        import shutil
        src = params["src_path"]; dst = params["dst_path"]
        try:
            # 디렉터리면 파일명 보존
            if os.path.isdir(dst):
                base = os.path.basename(src)
                dst = os.path.join(dst, base)
            shutil.copy2(src, dst)
            return ExecResult(ok=True, message=f"복사 완료: {src} → {dst}", shortcut="Ctrl+C, Ctrl+V")
        except Exception as e:
            return ExecResult(ok=False, message=f"복사 실패: {e}")

@register("delete_file")
class DeleteFileHandler(ActionHandler):
    async def execute(self, params: Dict[str, Any]) -> ExecResult:
        import os
        target = params["target_path"]
        try:
            if os.path.isdir(target):
                import shutil
                shutil.rmtree(target)
            else:
                os.remove(target)
            return ExecResult(ok=True, message=f"삭제 완료: {target}")
        except Exception as e:
            return ExecResult(ok=False, message=f"삭제 실패: {e}")

@register("rename_file")
class RenameFileHandler(ActionHandler):
    async def execute(self, params: Dict[str, Any]) -> ExecResult:
        import os
        old = params["old_path"]; new = params["new_path"]
        try:
            os.replace(old, new)
            return ExecResult(ok=True, message=f"이름 변경 완료: {old} → {new}")
        except Exception as e:
            return ExecResult(ok=False, message=f"이름 변경 실패: {e}")

@register("screenshot")
class ScreenshotHandler(ActionHandler):
    async def execute(self, params: Dict[str, Any]) -> ExecResult:
        # 예시: 외부 도구 호출 or pyautogui
        try:
            import datetime, pathlib
            import pyautogui
            save_path = params.get("save_path") or str(pathlib.Path.cwd() / f"screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            region = params.get("region", "full")
            if region == "full":
                img = pyautogui.screenshot()
                img.save(save_path)
            else:
                # 간단 예시 (active_window/custom은 실제 구현 필요)
                img = pyautogui.screenshot()
                img.save(save_path)
            return ExecResult(ok=True, message=f"스크린샷 저장: {save_path}")
        except Exception as e:
            return ExecResult(ok=False, message=f"스크린샷 실패: {e}")

@register("block_remote_access")
class BlockRemoteAccessHandler(ActionHandler):
    async def execute(self, params: Dict[str, Any]) -> ExecResult:
        # 실제 구현은 방화벽/서비스 설정 등을 다뤄야 함(위험 작업)
        enabled = bool(params.get("enabled"))
        # 여기서는 데모 메시지만
        state = "차단" if enabled else "해제"
        return ExecResult(ok=True, message=f"원격 접속 {state} 완료(데모)")

# ── 라우터(엔트리 포인트) ─────────────────────────────────────
async def execute_action(function_key: str, parameters: Dict[str, Any], shortcut: Optional[str] = None) -> Dict[str, Any]:
    """
    1) 파이썬 핸들러가 등록돼 있으면 그걸 사용
    2) 없으면 DB(functions)에서 script_command가 있으면 GenericScriptHandler로 실행
    3) 둘 다 없으면 오류
    """
    handler = _HANDLER_REGISTRY.get(function_key)

    if handler is None:
        # DB 조회해서 script_command가 있으면 스크립트 핸들러로 실행
        from .table_access import get_function_by_key  # 네가 만드는 작은 DAO
        row = get_function_by_key(function_key)  # {function_key, script_path, script_command, shortcut}
        if row and (row.get("script_path") or row.get("script_command")):
            handler = GenericScriptHandler(
                script_path=row.get("script_path") or "",
                script_command=row.get("script_command") or "",
                shortcut=row.get("shortcut"),
                shell="powershell"  # 필요 시 cmd/sh
            )
        else:
            return {"ok": False, "message": f"핸들러 없음: {function_key}"}

    res = await handler.execute(parameters or {})
    # 기존 IntentResponse와 호환되는 형태로 리턴
    return {
        "ok": res.ok,
        "message": res.message,
        "shortcut": res.shortcut or shortcut
    }


# 레지스트리(디스패처) + 플러그인 구조