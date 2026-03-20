# services/ui_guide_service.py
from dataclasses import dataclass
from typing import Optional, Dict, Any
import re

# 1) 기능별 "클릭 경로" 사전 (DB에 컬럼 없으니 하드코딩으로 시작)
#    필요 시 여기만 수정/추가하면 됨.
UI_GUIDES: Dict[str, Dict[str, str]] = {
    "open_taskmgr": {
        "click_path": "작업 표시줄을 우클릭 → '작업 관리자' 클릭",
    },
    "printer_reset": {
        "click_path": "설정 → 블루투스 및 장치 → 프린터 및 스캐너 → 해당 프린터 → '인쇄 대기열 열기' → 모두 취소",
        # 고급(관리자)용 PowerShell 권장 예시 (CMD 대신 PS 표기로)
        "admin_command": 'powershell -NoProfile -Command "Restart-Service -Name Spooler"',
        "advanced_note": "고급(관리자 권한 필요)",
        "risk_hint": "인쇄 작업이 모두 초기화될 수 있어요.",
    },
    "empty_recycle_bin": {
        "click_path": "바탕화면 '휴지통' 아이콘 우클릭 → '휴지통 비우기'",
        "admin_command": 'powershell -NoProfile -Command "Clear-RecycleBin -Force"',
        "advanced_note": "고급(빠른 비우기, 확인 없음)",
        "risk_hint": "되돌릴 수 없는 삭제입니다.",
    },
    "screenshot": {
        "click_path": "PrintScreen 키로 전체 캡처 / Windows+Shift+S 로 영역 캡처",
    },
    # 필요 시 계속 추가…
}

# 2) 위험도 간단 분류 (script_command 기준 보조 판정)
DANGEROUS_PATTERNS = [
    r"\bClear-RecycleBin\b", r"\bRemove-Item\b", r"\brm\s+-rf\b",
    r"\bFormat-Volume\b", r"\bmkfs\b",
]
CAUTION_PATTERNS = [r"\bchkdsk\b", r"\bDISM\b", r"\bsfc\s+/scannow\b", r"\bRestart-Service\b"]

def _classify_risk(script_command: Optional[str]) -> str:
    if not script_command:
        return "safe"
    s = script_command.lower()
    for p in DANGEROUS_PATTERNS:
        if re.search(p.lower(), s):
            return "danger"
    for p in CAUTION_PATTERNS:
        if re.search(p.lower(), s):
            return "caution"
    return "safe"

@dataclass
class Guide:
    title: str
    fastest: Optional[str] = None          # "가장 빠른 방법: **Ctrl+Shift+Esc**"
    click_path: Optional[str] = None       # "클릭 경로: ..."
    advanced_note: Optional[str] = None    # "고급(관리자 권한 필요)"
    admin_command: Optional[str] = None    # PowerShell 권장 명령 (CMD 대신)
    warning: Optional[str] = None          # 경고 문구
    requires_confirmation: bool = False    # 프론트 모달 트리거용

def _to_md(guide: Guide) -> str:
    parts = [f"### {guide.title}"]
    if guide.fastest:
        parts.append(guide.fastest)
    if guide.click_path:
        parts.append(f"클릭 경로: {guide.click_path}")
    if guide.advanced_note or guide.admin_command:
        if guide.advanced_note:
            parts.append(f"{guide.advanced_note}:")
        if guide.admin_command:
            parts.append("```powershell\n" + guide.admin_command + "\n```")
    if guide.warning:
        parts.append(f"\n> {guide.warning}")
    if guide.requires_confirmation:
        parts.append("\n**[확인 필요] 이 작업을 계속할까요?**")
    return "\n".join(parts)

def build_ui_guide(function_key: str, function_row: Dict[str, Any]) -> Dict[str, Any]:
    """
    function_row 예시:
    {
      "function_key": "open_taskmgr",
      "function_name": "작업 관리자 열기",
      "script_path": "scripts/xxx.cmd" 또는 None,
      "shortcut": "Ctrl+Shift+Esc" 또는 None,
      "script_command": "taskmgr.exe" 또는 None
    }
    """
    meta = UI_GUIDES.get(function_key, {})
    shortcut = function_row.get("shortcut")
    script_command = function_row.get("script_command")

    # ① 단축키가 있으면: 가장 빠른 방법 + 클릭 경로
    g = Guide(title=function_row.get("function_name") or function_key)
    if shortcut:
        g.fastest = f"가장 빠른 방법: **{shortcut}** 누르세요."
        if meta.get("click_path"):
            g.click_path = meta["click_path"]

    # ② 단축키는 없고 script_command만 있으면: 클릭 경로 + 고급(관리자) 명령(가능하면 PowerShell)
    if not shortcut and (script_command or meta.get("admin_command") or meta.get("click_path")):
        if meta.get("click_path"):
            g.click_path = meta["click_path"]
        # CMD만 가능한 .cmd/.bat 등이더라도, 사용자에게는 PowerShell 대안을 우선 안내
        g.advanced_note = meta.get("advanced_note") or "고급(관리자 권한 필요)"
        g.admin_command = meta.get("admin_command") or script_command

    # ③ 위험도/경고 (rule + meta 힌트)
    risk_level = _classify_risk(g.admin_command or script_command)
    if risk_level == "danger":
        g.warning = meta.get("risk_hint") or "⚠️ 되돌릴 수 없는 변경(영구 삭제 등)이 발생할 수 있습니다."
        g.requires_confirmation = True
    elif risk_level == "caution":
        g.warning = meta.get("risk_hint") or "주의가 필요한 작업입니다. 실행 전에 확인하세요."
        g.requires_confirmation = False

    return {
        "ok": True,
        "requires_confirmation": g.requires_confirmation,
        "message_markdown": _to_md(g),
        "payload": {
            "title": g.title,
            "fastest": g.fastest,
            "click_path": g.click_path,
            "advanced_note": g.advanced_note,
            "admin_command": g.admin_command,
            "warning": g.warning,
        },
    }
