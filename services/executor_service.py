# services/executor_service.py
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
    r"\bClear-RecycleBin\b", r"\bRemove-Item\b", r"\brm\s+-rf\b",
    r"\bFormat-Volume\b", r"\bmkfs\b",
]
CAUTION_PATTERNS = [
    r"\bchkdsk\b", r"\bDISM\b", r"\bsfc\s+/scannow\b",
    r"\bRestart-Service\b"
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

# ── 키 정규화(핫키용) ────────────────────────────────────────
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

def _normalize_key(k: str) -> str:
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

        # 위험도 판정 → exec.requiresConfirmation 플래그
        risk = _classify_risk(cmd)
        need_confirm = (risk in ("caution", "danger"))

        exec_plan = {
            **_new_exec_base(
                name="generic_script",
                preview=f"{self.shell} → {cmd}",
                requires_confirmation=need_confirm,
                timeout_ms=60000 if need_confirm else DEFAULT_TIMEOUT_MS
            ),
            "kind": "shell",
            "payload": {
                "shell": self.shell,          # "powershell" 권장
                "command": cmd,
                **({"cwd": self.cwd} if self.cwd else {})
            }
        }

        return PlanResult(
            ok=True,
            message="스크립트 실행 계획 생성",
            shortcut=self.shortcut,
            exec=exec_plan
        )

# ─────────────────────────────────────────────────────────────
# 예시: 커스텀 플래너(핫키)
# ─────────────────────────────────────────────────────────────
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
    1) 등록된 커스텀 플래너 우선
    2) 없으면 DB(functions) 조회 → GenericScriptPlanner 사용
    3) 둘 다 없으면 오류
    """
    planner = _HANDLER_REGISTRY.get(function_key)

    if planner is None:
        from .table_access import get_function_by_key
        row = get_function_by_key(function_key)
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
    return {"ok": res.ok, "message": res.message, "shortcut": res.shortcut or shortcut, "exec": res.exec}
