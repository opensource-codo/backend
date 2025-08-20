# services/executor_service.py
import asyncio
import os
import shlex
import uuid
from typing import Dict, Any, Callable, Awaitable, Optional
from dataclasses import dataclass
from jinja2 import Template

# 디자인 패턴 : 레지스트리 패턴
# 키 -> 객체/ 함수 매핑을 저장해 두는 전역 사전(Registry)을 만들어, 런타임에 찾아서 쓰는 패턴
# 실행해야 할 기능이 많을 때, if/elif/else나 switch 문으로 분기 -> 코드 복잡
# 새로운 기능 추가 시 기존 코드 수정 최소화 -> 확장성 높음, 플러그인 구조 구현에 유리

# 나중에 단순 스크립트로 처리하기 어렵거나 복잡한 로직(전처리, 검증, OS별 분기 등), 파라미터 유효성 검사, 마우스 제어, 포커스 전환, 별칭, 권한 레벨 등 필요 시
# 현재는 DB 기반
# 레지스트리 승격 필요 : screenshot, active_window 캡처, 창 정렬, 특정 앱 실행 후 상태 확인, 민감 작업, 입력 검증 기능별로 크게 다를 경우 

_HANDLER_REGISTRY: Dict[str, "ActionPlanner"] = {}

# TODO : 레지스트리 기능 추가 및 수정 - 현재는 DB 기반

def register(function_key: str):
    """클래스를 전역 플래너 레지스트리에 등록하는 데코레이터"""
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
    exec: Optional[Dict[str, Any]] = None  # 실제 실행 스펙(Electron에서 실행)


class ActionPlanner:
    """플래너 베이스: 실행 '계획'만 생성한다(실행 금지)."""
    async def plan(self, params: Dict[str, Any]) -> PlanResult:
        raise NotImplementedError

# ─────────────────────────────────────────────────────────────
# 안전 설정
# ─────────────────────────────────────────────────────────────

SAFE_SHELLS = {"powershell", "pwsh", "cmd", "sh", "bash"}
DEFAULT_SHELL = "powershell"
DEFAULT_CWD = None  # 필요 시 고정 디렉터리 경로로 지정 가능 (예: "C:\\Program Files\\MyApp\\scripts")
DEFAULT_TIMEOUT_MS = 15000

FORBIDDEN_TOKENS = {"&&", "||", "|", ";", "`", "$(", "<(", ">", ">>"}  # 아주 기초적인 차단 토큰

def _new_exec_base(name: str, preview: Optional[str] = None,
                   requires_confirmation: Optional[bool] = None,
                   timeout_ms: Optional[int] = None) -> Dict[str, Any]:
    # TODO : id 
    return {
        "version": 1,
        "id": str(uuid.uuid4()),
        "name": name,
        **({"preview": preview} if preview else {}),
        **({"requiresConfirmation": bool(requires_confirmation)} if requires_confirmation is not None else {}),
        **({"timeoutMs": int(timeout_ms)} if timeout_ms else {"timeoutMs": DEFAULT_TIMEOUT_MS}),
    }
    
# ── 키 이름 정규화(핫키용) ─────────────────────────────────────
_KEY_NORMALIZE_MAP = {
    "control": "ctrl",
    "ctrl": "ctrl",
    "shift": "shift",
    "alt": "alt",
    "option": "alt",
    "cmd": "meta",
    "command": "meta",
    "meta": "meta",
    "win": "meta",
    "super": "meta",
    "enter": "enter",
    "return": "enter",
    "esc": "escape",
    "escape": "escape",
    "del": "delete",
    "delete": "delete",
    "bksp": "backspace",
    "backspace": "backspace",
    "space": "space",
    "tab": "tab",
    # 문자키/기타는 소문자 그대로 사용 가정
}

def _normalize_key(k: str) -> str:
    s = (k or "").strip().lower()
    return _KEY_NORMALIZE_MAP.get(s, s)

def _sanitize_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    매우 얕은 1차 방어선:
    - 타입: str/int/float/bool/None만 허용
    - 문자열 값에 위험 토큰이 포함되면 거부
    """
    safe: Dict[str, Any] = {}
    for k, v in (params or {}).items():
        if isinstance(v, (int, float, bool)) or v is None:
            safe[k] = v
        elif isinstance(v, str):
            s = v.strip()
            if any(tok in s for tok in FORBIDDEN_TOKENS):
                # 위험 토큰이 있으면 빈 값으로 대체(또는 raise 후 상위에서 처리)
                continue
            safe[k] = s
        # 그 외 타입(list/dict 등)은 템플릿 바인딩 대상에서 제외(필요시 명시적으로 허용)
    return safe


def _render_safe(cmd_tpl: str, context: Dict[str, Any]) -> str:
    """Jinja2 템플릿 바인딩(쉘 실행은 클라이언트에서 함)"""
    return Template(cmd_tpl).render(**context)


# ─────────────────────────────────────────────────────────────
# DB 기반 제너릭 플래너
# ─────────────────────────────────────────────────────────────

class GenericScriptPlanner(ActionPlanner):
    """
    functions 테이블의 (script_path, script_command, shell, shortcut)를 이용해
    실행 계획만 생성한다. 실제 실행은 Electron이 담당한다.
    """
    def __init__(
        self,
        script_path: str,
        script_command: str,
        shell: str = DEFAULT_SHELL,
        shortcut: Optional[str] = None,
        cwd: Optional[str] = DEFAULT_CWD,
    ):
        self.script_path = script_path or ""
        self.script_command = script_command or ""
        self.shell = (shell or DEFAULT_SHELL).lower()
        self.shortcut = shortcut
        self.cwd = cwd

    async def plan(self, params: Dict[str, Any]) -> PlanResult:
        if self.shell not in SAFE_SHELLS and self.shell not in {"python", "node"}:
            return PlanResult(ok=False, message=f"허용되지 않은 셸: {self.shell}")

        # 사용자 파라미터 얕은 정규화
        safe_params = _sanitize_params(params)
        context = {"SCRIPT_PATH": self.script_path, **safe_params}

        if self.script_command:
            cmd = _render_safe(self.script_command, context)
        elif self.script_path:
            # 명령 템플릿이 없으면 스크립트 경로를 직접 실행하는 형태로 전달
            # (클라이언트에서 셸/실행 방법을 결정)
            cmd = f'"{self.script_path}"'
        else:
            return PlanResult(ok=False, message="실행 가능한 스크립트 정보가 없습니다.")

        return PlanResult(
            ok=True,
            message="스크립트 실행 계획 생성",
            shortcut=self.shortcut,
            exec={
                "type": self.shell,             # "powershell" | "cmd" | "sh"
                "name": "generic_script",       # 클라이언트 허용리스트 키와 일치
                "args": {
                    "command": cmd,
                    **({"cwd": self.cwd} if self.cwd else {})
                }
            }
        )


# ─────────────────────────────────────────────────────────────
# 예시: 커스텀 플래너(핫키)
# ─────────────────────────────────────────────────────────────

@register("paste")
class PastePlanner(ActionPlanner):
    async def plan(self, params: Dict[str, Any]) -> PlanResult:
        # 키 콤보 표준화
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
                "combo": combo,                 # 예: ["ctrl","v"]
                "repeat": 1,
                "delayMsBetweenKeys": 20
            }
        }

        return PlanResult(
            ok=True,
            message="붙여넣기 단축키 실행 계획",
            shortcut="Ctrl+V",
            exec=exec_plan
        )


# ─────────────────────────────────────────────────────────────
# 엔트리 포인트: 플래너 선택 → 계획 생성
# ─────────────────────────────────────────────────────────────

async def plan_action(function_key: str, parameters: Dict[str, Any], shortcut: Optional[str] = None) -> Dict[str, Any]:
    """
    1) 레지스트리에 커스텀 플래너가 있으면 그걸 사용 : 현재는 X 
    2) 없으면 DB(functions)에서 script_command/script_path로 GenericScriptPlanner 사용
    3) 둘 다 없으면 오류
    """
    planner = _HANDLER_REGISTRY.get(function_key)

    if planner is None:
        # 레지스트리에 없으면 DB 조회
        from .table_access import get_function_by_key  # {function_key, script_path, script_command, shell, shortcut}
        row = get_function_by_key(function_key)

        if row and (row.get("script_path") or row.get("script_command")):
            planner = GenericScriptPlanner(
                script_path=row.get("script_path") or "",
                script_command=row.get("script_command") or "",
                shell=(row.get("shell") or DEFAULT_SHELL),
                shortcut=row.get("shortcut"),
                # cwd=None,  # 필요 시 고정 작업디렉터리 지정
            )
        else:
            return {"ok": False, "message": f"플래너 없음: {function_key}"}

    res: PlanResult = await planner.plan(parameters or {})
    return {
        "ok": res.ok,
        "message": res.message,
        "shortcut": res.shortcut or shortcut,
        "exec": res.exec
    }
    