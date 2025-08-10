from __future__ import annotations

import os
import re
import shutil
import asyncio
import sqlite3
import datetime
import platform
from typing import Any, Dict, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# DB 유틸
# ─────────────────────────────────────────────────────────────────────────────
def _get_conn(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def _resolve_function_by_intent(intent: str, db_path: str = "assistant.db") -> Dict[str, Optional[str]]:
    """
    intents → functions 조인으로 function_key, function_name, shortcut, script_path/command 조회
    스키마에 맞게 JOIN 키를 조정하세요.
    """
    with _get_conn(db_path) as conn:
        # 스키마 A) intents.function_id ↔ functions.id
        row = conn.execute(
            """
            SELECT
                f.function_key,
                f.function_name,
                f.shortcut,
                f.script_path,
                f.script_command
            FROM intents i
            LEFT JOIN functions f ON i.function_id = f.id
            WHERE i.intent = ?
            """,
            (intent,),
        ).fetchone()

        if row:
            return dict(row)

    # 폴백: 못 찾으면 None
    return {
        "function_key": None,
        "function_name": None,
        "shortcut": None,
        "script_path": None,
        "script_command": None,
    }

# ─────────────────────────────────────────────────────────────────────────────
# 퍼블릭 API
# ─────────────────────────────────────────────────────────────────────────────
async def execute_action(intent: str, params: Dict[str, Any], db_path: str = "assistant.db") -> Dict[str, Any]:
    """
    비동기 실행 엔트리포인트.
    - intent로 function_key를 해석하고,
    - 해당 핸들러를 호출하여 작업 수행
    반환: {"message": str, "shortcut": Optional[str]}
    """
    info = _resolve_function_by_intent(intent, db_path=db_path)
    function_key = (info.get("function_key") or "").strip()

    # function_key가 비어있으면 intent 문자열로도 한 번 매칭 시도(유연성)
    if not function_key:
        function_key = _guess_function_key_from_intent(intent)

    shortcut = info.get("shortcut")

    # 라우팅
    if function_key == "copy_file":
        msg = await _handle_copy_file(params)
    elif function_key == "delete_file":
        msg = await _handle_delete_file(params)
    elif function_key == "rename_file":
        msg = await _handle_rename_file(params)
    elif function_key == "screenshot":
        msg = await _handle_screenshot(params)
    elif function_key == "block_remote_access":
        msg = await _handle_block_remote_access(params)
    else:
        # 스크립트 기반 기능 지원(선택): functions.script_command/script_path가 있으면 실행
        msg = await _maybe_run_script(info, params)
        if msg is None:
            return {
                "message": f"알 수 없는 기능입니다. (intent='{intent}', function_key='{function_key}')",
                "shortcut": shortcut,
            }

    return {"message": msg, "shortcut": shortcut}

def _guess_function_key_from_intent(intent: str) -> str:
    s = intent.strip().lower()
    if any(k in s for k in ["복사", "copy"]):
        return "copy_file"
    if any(k in s for k in ["삭제", "지워", "remove", "delete"]):
        return "delete_file"
    if any(k in s for k in ["이름 바꿔", "이름변경", "rename"]):
        return "rename_file"
    if any(k in s for k in ["캡쳐", "캡처", "스크린샷", "screenshot"]):
        return "screenshot"
    if any(k in s for k in ["원격", "remote", "rdp", "접속 차단", "차단", "해제"]):
        return "block_remote_access"
    return ""

# ─────────────────────────────────────────────────────────────────────────────
# 핸들러들
# ─────────────────────────────────────────────────────────────────────────────
async def _handle_copy_file(params: Dict[str, Any]) -> str:
    src = params.get("src_path")
    dst = params.get("dst_path")
    if not src or not dst:
        return "복사 실패: src_path/dst_path가 필요합니다."

    # 경로 정규화
    src = _norm_path(src)
    dst = _norm_path(dst)

    if not os.path.exists(src):
        return f"복사 실패: 원본이 없습니다: {src}"

    # 목적지가 디렉터리인지 판단
    dst_is_dir = _looks_like_dir(dst) or os.path.isdir(dst)
    if dst_is_dir:
        os.makedirs(dst, exist_ok=True)
        dst_file = os.path.join(dst, os.path.basename(src))
    else:
        # 상위 디렉터리 생성
        parent = os.path.dirname(dst)
        if parent:
            os.makedirs(parent, exist_ok=True)
        dst_file = dst

    async def _copy():
        await asyncio.to_thread(shutil.copy2, src, dst_file)

    try:
        await _copy()
        return f"복사 완료: {src} → {dst_file}"
    except Exception as e:
        return f"복사 실패: {e}"

async def _handle_delete_file(params: Dict[str, Any]) -> str:
    target = params.get("target_path")
    force = bool(params.get("force", False))
    if not target:
        return "삭제 실패: target_path가 필요합니다."

    target = _norm_path(target)
    if not os.path.exists(target):
        return f"삭제 실패: 대상이 없습니다: {target}"

    try:
        if os.path.isdir(target):
            if force:
                await asyncio.to_thread(shutil.rmtree, target)
                return f"디렉토리 삭제 완료: {target}"
            else:
                return "삭제 실패: 디렉토리입니다. force=True가 필요합니다."
        else:
            await asyncio.to_thread(os.remove, target)
            return f"파일 삭제 완료: {target}"
    except Exception as e:
        return f"삭제 실패: {e}"

async def _handle_rename_file(params: Dict[str, Any]) -> str:
    old = params.get("old_path")
    new = params.get("new_path")
    if not old or not new:
        return "이름 변경 실패: old_path/new_path가 필요합니다."

    old = _norm_path(old)
    new = _norm_path(new)

    if not os.path.exists(old):
        return f"이름 변경 실패: 대상이 없습니다: {old}"
    if os.path.exists(new):
        return f"이름 변경 실패: 새 경로가 이미 존재합니다: {new}"

    # 상위 디렉터리 보장
    parent = os.path.dirname(new)
    if parent:
        os.makedirs(parent, exist_ok=True)

    try:
        await asyncio.to_thread(os.rename, old, new)
        return f"이름 변경 완료: {old} → {new}"
    except Exception as e:
        return f"이름 변경 실패: {e}"

async def _handle_screenshot(params: Dict[str, Any]) -> str:
    region = (params.get("region") or "full").lower()
    save_path = params.get("save_path")

    # 기본 저장 경로
    if not save_path:
        base = os.path.join(os.path.expanduser("~"), "Pictures", "Screenshots")
        os.makedirs(base, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = os.path.join(base, f"screenshot_{ts}.png")

    save_path = _norm_path(save_path)
    # 상위 디렉터리 보장
    parent = os.path.dirname(save_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    try:
        # Pillow가 필요
        try:
            from PIL import ImageGrab
        except Exception:
            return "스크린샷 실패: Pillow가 필요합니다. `pip install pillow` 후 다시 시도해 주세요."

        if region != "full":
            # 간단화: active_window/custom 미지원 안내
            region = "full"

        img = await asyncio.to_thread(ImageGrab.grab)  # 전체 화면
        await asyncio.to_thread(img.save, save_path)
        return f"스크린샷 저장 완료: {save_path}"
    except Exception as e:
        return f"스크린샷 실패: {e}"

async def _handle_block_remote_access(params: Dict[str, Any]) -> str:
    """
    Windows에서 RDP(원격 데스크톱) 허용/차단을 토글.
    - 관리자 권한 필요.
    - 레지스트리: fDenyTSConnections (1=차단, 0=허용)
    - 방화벽 규칙: Remote Desktop 그룹 enable yes/no
    """
    enabled = params.get("enabled")
    if enabled is None:
        return "원격 접속 설정 실패: enabled=True/False가 필요합니다."

    if platform.system().lower() != "windows":
        return "원격 접속 설정 실패: 이 기능은 Windows에서만 지원됩니다."

    # 관리자 권한 체크
    if not _is_admin_windows():
        return "원격 접속 설정 실패: 관리자 권한이 필요합니다. 관리자 권한으로 다시 실행해 주세요."

    # 명령 조립
    if enabled:  # 차단(접속 불가)
        reg_cmd = r'reg add "HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server" /v fDenyTSConnections /t REG_DWORD /d 1 /f'
        fw_cmd  = r'netsh advfirewall firewall set rule group="remote desktop" new enable=no'
        action_text = "차단"
    else:        # 허용(접속 가능)
        reg_cmd = r'reg add "HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server" /v fDenyTSConnections /t REG_DWORD /d 0 /f'
        fw_cmd  = r'netsh advfirewall firewall set rule group="remote desktop" new enable=yes'
        action_text = "허용"

    try:
        # 동기 명령을 비동기로 래핑
        proc1 = await asyncio.create_subprocess_shell(reg_cmd)
        await proc1.communicate()
        if proc1.returncode != 0:
            return f"원격 접속 {action_text} 실패: 레지스트리 명령 오류"

        proc2 = await asyncio.create_subprocess_shell(fw_cmd)
        await proc2.communicate()
        if proc2.returncode != 0:
            return f"원격 접속 {action_text} 실패: 방화벽 명령 오류"

        return f"원격 접속 {action_text} 완료"
    except Exception as e:
        return f"원격 접속 설정 실패: {e}"
    
# 기존 함수를 이 버전으로 교체
async def _maybe_run_script(info: Dict[str, Any], params: Dict[str, Any]) -> Optional[str]:
    """
    외부 스크립트 실행.
    - functions.script_command 안의 플레이스홀더({src_path}, ${dst_path}, {script_path} 등)를 params로 바인딩
    - script_command가 없으면 script_path만 실행
    - Windows shell 기준으로 안전하게 인자 쿼팅
    """
    script_cmd = (info.get("script_command") or "").strip()
    script_path = (info.get("script_path") or "").strip()

    if not script_cmd and not script_path:
        return None

    # 바인딩에 사용할 공통 파라미터 구성
    bind_params: Dict[str, Any] = {}
    bind_params.update(params or {})
    if script_path:
        bind_params.setdefault("script_path", _norm_path(script_path))

    # 템플릿(커맨드 라인) 결정
    template = script_cmd if script_cmd else '"{script_path}"'

    # 템플릿 렌더링 (플레이스홀더 치환 + 안전 쿼팅)
    try:
        final_cmd = _render_command_template(template, bind_params)
    except KeyError as ke:
        missing = str(ke).strip("'")
        return f"외부 스크립트 실행 실패: 필요한 파라미터 '{missing}'가 없습니다."
    except Exception as e:
        return f"외부 스크립트 준비 중 오류: {e}"

    try:
        # 실제 실행
        proc = await asyncio.create_subprocess_shell(final_cmd)
        await proc.communicate()
        if proc.returncode == 0:
            return "외부 스크립트 실행 완료"
        return f"외부 스크립트 실행 실패(returncode={proc.returncode})"
    except Exception as e:
        return f"외부 스크립트 실행 중 오류: {e}"
    
# ─────────────────────────────────────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────────────────────────────────────
_ALLOWED_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
def _norm_path(p: str) -> str:
    # 따옴표/슬래시 정리
    s = str(p).strip().strip('"').strip("'").replace("/", "\\")
    try:
        return os.path.normpath(s)
    except Exception:
        return s

def _looks_like_dir(path: str) -> bool:
    # 끝이 백슬래시면 디렉터리로 간주
    return bool(path) and (path.endswith("\\") or path.endswith("/"))

def _is_admin_windows() -> bool:
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

def _render_command_template(template: str, params: Dict[str, Any]) -> str:
    """
    템플릿 안의 {name} 또는 ${name} 플레이스홀더를 params로 치환.
    - 모든 값은 Windows shell 안전을 위해 항상 쿼팅
    - 알 수 없는 플레이스홀더가 있으면 KeyError
    """
    # 1) 치환용 사전 만들기 (문자열화 + 경로 정규화 + 안전 쿼팅)
    prepared: Dict[str, str] = {}
    for k, v in (params or {}).items():
        if not isinstance(k, str) or not _ALLOWED_KEY.match(k):
            # 키 이름은 안전한 식별자만 허용
            continue
        s = _stringify_and_normalize_param(k, v)
        prepared[k] = _quote_arg_windows(s)

    # 2) ${name} 형태 먼저 치환
    def sub_dollar(match: re.Match) -> str:
        key = match.group(1)
        if key not in prepared:
            raise KeyError(key)
        return prepared[key]

    cmd = re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", sub_dollar, template)

    # 3) {name} 형태 치환 (중괄호 이스케이프 {{ }}는 그대로 둠)
    def sub_brace(match: re.Match) -> str:
        key = match.group(1)
        if key not in prepared:
            raise KeyError(key)
        return prepared[key]

    # 중괄호 플레이스홀더만 치환 ({{,}}는 유지)
    cmd = re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", sub_brace, cmd)

    return cmd

def _stringify_and_normalize_param(key: str, value: Any) -> str:
    """경로/불리언/기타 타입에 대한 문자열화와 경로 정규화."""
    if value is None:
        return ""
    # 경로 힌트: *_path, path, src, dst 등은 경로 정규화
    if key.lower().endswith("_path") or key.lower() in {"path", "src", "dst", "script_path"}:
        return _norm_path(str(value))
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)

def _quote_arg_windows(arg: str) -> str:
    """
    Windows shell용 안전 쿼팅:
    - 내부 " 를 \" 로 이스케이프
    - 항상 전체를 "..." 로 감싸기
    - 백슬래시/공백/특수문자 케이스를 단순화하여 안전성 확보
    """
    if arg is None:
        arg = ""
    # 내부 따옴표 이스케이프
    arg = str(arg).replace('"', r'\"')
    # 끝이 백슬래시로 끝나는 경우, Windows cmd의 인용규칙상 문제가 될 수 있으니 하나 더 붙여줌
    if arg.endswith("\\"):
        arg = arg + "\\"
    return f'"{arg}"'
