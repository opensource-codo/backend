import asyncio
import os
import shlex
import re
import uuid
from typing import Dict, Any, Optional
from dataclasses import dataclass
from jinja2 import Template

# ─────────────────────────────────────────────────────────────
# 레지스트리
# ─────────────────────────────────────────────────────────────
_HANDLER_REGISTRY: Dict[str, "ActionPlanner"] = {}

# TODO : 레지스트리 기능 추가 및 수정 - 현재는 DB 기반

def register(function_key: str):
    def deco(cls):
        _HANDLER_REGISTRY[function_key] = cls()
        return cls
    return deco

# ─────────────────────────────────────────────────────────────
# 공통 타입
# ─────────────────────────────────────────────────────────────
@dataclass
class PlanResult:
    ok: bool
    message: str
    shortcut: Optional[str] = None
    exec: Optional[Dict[str, Any]] = None

class ActionPlanner:
    async def plan(self, params: Dict[str, Any]) -> PlanResult:
        raise NotImplementedError

# ─────────────────────────────────────────────────────────────
# 안전 설정 / 유틸
# ─────────────────────────────────────────────────────────────
SAFE_SHELLS = {"powershell", "pwsh", "cmd", "sh", "bash"}
DEFAULT_SHELL = "powershell"
DEFAULT_CWD = None
DEFAULT_TIMEOUT_MS = 15000
FORBIDDEN_TOKENS = {"&&", "||", "|", ";", "`", "$(", "<(", ">", ">>"}

DANGEROUS_PATTERNS = [
    r"\bClear-RecycleBin\b",
    r"\bRemove-Item\b",
    r"\brm\s+-rf\b",
    r"\bFormat-Volume\b",
    r"\bmkfs\b",
    r"\bshutdown\b",
]
CAUTION_PATTERNS = [
    r"\bchkdsk\b",
    r"\bDISM\b",
    r"\bsfc\s+/scannow\b",
    r"\bRestart-Service\b",
]

def _classify_risk(command: Optional[str]) -> str:
    if not command:
        return "safe"
    s = command.lower()
    for p in DANGEROUS_PATTERNS:
        if re.search(p.lower(), s):
            return "danger"
    for p in CAUTION_PATTERNS:
        if re.search(p.lower(), s):
            return "caution"
    return "safe"

def _new_exec_base(name: str,
                   preview: Optional[str] = None,
                   requires_confirmation: Optional[bool] = None,
                   timeout_ms: Optional[int] = None) -> Dict[str, Any]:
    d = {
        "version": 1,
        "id": str(uuid.uuid4()),
        "name": name,
        "timeoutMs": int(timeout_ms) if timeout_ms else DEFAULT_TIMEOUT_MS,
    }
    if preview:
        d["preview"] = preview
    if requires_confirmation is not None:
        d["requiresConfirmation"] = bool(requires_confirmation)
    return d

def _normalize_key(k: str) -> str:
    _KEY_NORMALIZE_MAP = {
        "control": "ctrl", "ctrl": "ctrl",
        "shift": "shift", "alt": "alt", "option": "alt",
        "cmd": "meta", "command": "meta", "meta": "meta", "win": "meta", "super": "meta",
        "enter": "enter", "return": "enter",
        "esc": "escape", "escape": "escape",
        "del": "delete", "delete": "delete",
        "bksp": "backspace", "backspace": "backspace",
        "space": "space", "tab": "tab",
    }
    s = (k or "").strip().lower()
    return _KEY_NORMALIZE_MAP.get(s, s)

def _sanitize_params(params: Dict[str, Any]) -> Dict[str, Any]:
    safe: Dict[str, Any] = {}
    for k, v in (params or {}).items():
        if isinstance(v, (int, float, bool)) or v is None:
            safe[k] = v
        elif isinstance(v, str):
            s = v.strip()
            if any(tok in s for tok in FORBIDDEN_TOKENS):
                continue
            safe[k] = s
    return safe

def _render_safe(cmd_tpl: str, context: Dict[str, Any]) -> str:
    return Template(cmd_tpl).render(**context)

def _ps_quote(s: str) -> str:
    """PowerShell용 작은따옴표 이스케이프."""
    s = str(s).replace("'", "''")
    return f"'{s}'"

def _make_shell_exec(name: str, cmd: str, shortcut: Optional[str] = None) -> PlanResult:
    risk = _classify_risk(cmd)
    need_confirm = (risk in ("caution", "danger"))
    exec_plan = {
        **_new_exec_base(
            name=name,
            preview=f"{DEFAULT_SHELL} → {cmd}",
            requires_confirmation=need_confirm,
            timeout_ms=60000 if need_confirm else DEFAULT_TIMEOUT_MS,
        ),
        "kind": "shell",
        "payload": {
            "shell": DEFAULT_SHELL,
            "command": cmd,
        },
    }
    return PlanResult(ok=True, message="실행 계획 생성", shortcut=shortcut, exec=exec_plan)

# ─────────────────────────────────────────────────────────────
# DB 기반 제너릭 플래너
# ─────────────────────────────────────────────────────────────
class GenericScriptPlanner(ActionPlanner):
    """
    functions(script_path, script_command, shortcut[, shell])를 사용해 '실행 계획'만 만든다.
    실제 실행은 클라이언트가 수행.
    """
    def __init__(self,
                 script_path: str,
                 script_command: str,
                 shortcut: Optional[str] = None,
                 cwd: Optional[str] = DEFAULT_CWD,
                 shell: str = DEFAULT_SHELL):
        self.script_path = script_path or ""
        self.script_command = script_command or ""
        self.shortcut = shortcut
        self.cwd = cwd
        self.shell = (shell or DEFAULT_SHELL).lower()

    async def plan(self, params: Dict[str, Any]) -> PlanResult:
        if self.shell not in SAFE_SHELLS and self.shell not in {"python", "node"}:
            return PlanResult(ok=False, message=f"허용되지 않은 셸: {self.shell}")

        safe_params = _sanitize_params(params)
        context = {"SCRIPT_PATH": self.script_path, **safe_params}

        if self.script_command:
            cmd = _render_safe(self.script_command, context)
        elif self.script_path:
            # 템플릿이 없으면 경로 자체를 실행 커맨드로 전달 (클라가 처리)
            cmd = f'"{self.script_path}"'
        else:
            return PlanResult(ok=False, message="실행 가능한 스크립트 정보가 없습니다.")

        # preview는 "<shell> → <command>"
        risk = _classify_risk(cmd)
        need_confirm = (risk in ("caution", "danger"))

        exec_plan = {
            **_new_exec_base(
                name="generic_script",
                preview=f"{self.shell} → {cmd}",
                requires_confirmation=need_confirm,
                timeout_ms=60000 if need_confirm else DEFAULT_TIMEOUT_MS,
            ),
            "kind": "shell",
            "payload": {
                "shell": self.shell,
                "command": cmd,
                **({"cwd": self.cwd} if self.cwd else {}),
            },
        }
        return PlanResult(ok=True, message="스크립트 실행 계획 생성", shortcut=self.shortcut, exec=exec_plan)

# ─────────────────────────────────────────────────────────────
# 빌트인 커스텀 플래너들
# ─────────────────────────────────────────────────────────────
@register("create_folder")
class CreateFolderPlanner(ActionPlanner):
    async def plan(self, params: Dict[str, Any]) -> PlanResult:
        p = _sanitize_params(params)
        path = p.get("path")
        name = p.get("name")
        if not path or not name:
            return PlanResult(ok=False, message="필수 파라미터 누락: path, name")
        cmd = f"New-Item -ItemType Directory -Path {_ps_quote(path)} -Name {_ps_quote(name)} -Force"
        return _make_shell_exec("create_folder", cmd)

@register("copy_file")
class CopyFilePlanner(ActionPlanner):
    async def plan(self, params: Dict[str, Any]) -> PlanResult:
        p = _sanitize_params(params)
        src = p.get("src_path")
        dst = p.get("dst_path")
        if not src or not dst:
            return PlanResult(ok=False, message="필수 파라미터 누락: src_path, dst_path")
        cmd = f"Copy-Item -Path {_ps_quote(src)} -Destination {_ps_quote(dst)} -Force"
        return _make_shell_exec("copy_file", cmd)

@register("move_file")
class MoveFilePlanner(ActionPlanner):
    async def plan(self, params: Dict[str, Any]) -> PlanResult:
        p = _sanitize_params(params)
        src = p.get("src_path")
        dst = p.get("dst_path")
        if not src or not dst:
            return PlanResult(ok=False, message="필수 파라미터 누락: src_path, dst_path")
        cmd = f"Move-Item -Path {_ps_quote(src)} -Destination {_ps_quote(dst)} -Force"
        return _make_shell_exec("move_file", cmd)

@register("rename_file")
class RenameFilePlanner(ActionPlanner):
    async def plan(self, params: Dict[str, Any]) -> PlanResult:
        p = _sanitize_params(params)
        old_path = p.get("old_path")
        new_path = p.get("new_path")
        new_name = p.get("new_name") or (os.path.basename(str(new_path)) if new_path else None)
        if not old_path or not new_name:
            return PlanResult(ok=False, message="필수 파라미터 누락: old_path, new_name(또는 new_path)")
        cmd = f"Rename-Item -Path {_ps_quote(old_path)} -NewName {_ps_quote(new_name)} -Force"
        return _make_shell_exec("rename_file", cmd)

@register("empty_recycle_bin")
class EmptyRecycleBinPlanner(ActionPlanner):
    async def plan(self, params: Dict[str, Any]) -> PlanResult:
        cmd = "Clear-RecycleBin -Force"
        # 위험 분류에 의해 requiresConfirmation 자동 True
        return _make_shell_exec("empty_recycle_bin", cmd)

@register("shutdown")
class ShutdownPlanner(ActionPlanner):
    async def plan(self, params: Dict[str, Any]) -> PlanResult:
        cmd = "shutdown /r /t 0"
        # 위험 분류에 의해 requiresConfirmation 자동 True
        return _make_shell_exec("shutdown", cmd)

# 추가: 제어판 열기
@register("open_control_panel")
class OpenControlPanelPlanner(ActionPlanner):
    async def plan(self, params: Dict[str, Any]) -> PlanResult:
        # 단순 실행: control.exe
        cmd = "control.exe"
        return _make_shell_exec("open_control_panel", cmd, shortcut="Win+R → control")

# (예시) 커스텀 플래너: 핫키
@register("paste")
class PastePlanner(ActionPlanner):
    async def plan(self, params: Dict[str, Any]) -> PlanResult:
        raw_combo = params.get("combo") or ["control", "v"]
        combo = [_normalize_key(k) for k in raw_combo]
        exec_plan = {
            **_new_exec_base(
                name="paste",
                preview="Send CTRL+V",
                requires_confirmation=False,
                timeout_ms=3000
            ),
            "kind": "hotkey",
            "payload": {
                "combo": combo,
                "repeat": 1,
                "delayMsBetweenKeys": 20
            }
        }
        return PlanResult(ok=True, message="붙여넣기 단축키 실행 계획", shortcut="Ctrl+V", exec=exec_plan)

# ─────────────────────────────────────────────────────────────
# 엔트리 포인트
# ─────────────────────────────────────────────────────────────
async def plan_action(function_key: str, parameters: Dict[str, Any], shortcut: Optional[str] = None) -> Dict[str, Any]:
    """
    1) 레지스트리에 커스텀 플래너가 있으면 그걸 사용
    2) 없으면 DB(functions)에서 script_command/Path로 GenericScriptPlanner 사용
    3) 둘 다 없으면 오류
    """
    planner = _HANDLER_REGISTRY.get((function_key or "").strip().lower())

    if planner is None:
        # DB 폴백
        try:
            from .table_access import get_function_by_key
        except Exception:
            get_function_by_key = None

        row = None
        if get_function_by_key:
            try:
                row = get_function_by_key((function_key or "").strip().lower())
            except Exception:
                row = None

        if row and (row.get("script_path") or row.get("script_command")):
            planner = GenericScriptPlanner(
                script_path=row.get("script_path") or "",
                script_command=row.get("script_command") or "",
                shortcut=row.get("shortcut"),
                cwd=None,
                shell=(row.get("shell") or DEFAULT_SHELL),
            )
        else:
            return {"ok": False, "message": f"플래너 없음: {function_key}"}

    res: PlanResult = await planner.plan(parameters or {})
    return {
        "ok": res.ok,
        "message": res.message,
        "shortcut": res.shortcut or shortcut,
        "exec": res.exec,
    }