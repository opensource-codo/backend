# services/guide_service.py
from __future__ import annotations

import os
import re
from typing import Optional, Dict, Any, Tuple
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ─────────────────────────────────────────────────────────────
# UI/명령어 매핑 메타 (빠른 운영용; 나중에 DB로 이관 가능)
# ─────────────────────────────────────────────────────────────
UI_GUIDES: Dict[str, Dict[str, Any]] = {
    "open_taskmgr": {
        "ui_path": "작업 표시줄을 우클릭 → '작업 관리자' 클릭",
        "admin_required": False,
        "risk_level": "safe",
    },
    "empty_recycle_bin": {
        "ui_path": "바탕화면 '휴지통' 아이콘 우클릭 → '휴지통 비우기'",
        "admin_required": False,
        "risk_level": "danger",
        "notes": "삭제 후 복구가 어렵습니다.",
        # 순수 PowerShell cmdlet만 표기
        "admin_command": "Clear-RecycleBin -Force",
    },
    "check_disk": {
        "ui_path": "파일 탐색기 → C: 드라이브 우클릭 → '속성' → '도구' 탭 → '오류 검사'",
        "admin_required": True,
        "risk_level": "caution",
        "notes": "명령 실행 시 재부팅이 필요할 수 있습니다.",
        "admin_command": "chkdsk C: /f",
    },
    "flush_dns": {
        "ui_path": "설정 → 네트워크 및 인터넷 → 고급 네트워크 설정 → 네트워크 초기화",
        "admin_required": True,
        "risk_level": "safe",
        "notes": "PowerShell 네이티브 명령 예: Clear-DnsClientCache",
        # PS 네이티브로 교체
        "admin_command": "Clear-DnsClientCache",
    },
}

# ─────────────────────────────────────────────────────────────
# 위험도/관리자 권한 휴리스틱
# ─────────────────────────────────────────────────────────────
_DANGEROUS_PATTERNS = [
    r"\bclear-recyclebin\b",
    r"\bremove-item\b",
    r"\brm\s+-rf\b",
    r"\bformat-volume\b",
    r"\bmkfs\b",
    r"\bshutdown\b",
    r"\bdel\s+",
]
_CAUTION_PATTERNS = [
    r"\bchkdsk\b",
    r"\bdism\b",
    r"\bsfc\s+/scannow\b",
    r"\brestart-service\b",
    r"\bnetsh\b",
    r"\breg\s+(add|delete|query)\b",
    r"\bschtasks\b",
    r"\bpowercfg\b",
]

def _classify_risk_by_cmd(cmd: Optional[str]) -> Tuple[str, bool]:
    """
    명령 문자열 기반 위험도 및 관리자 권한 필요 여부를 추정.
    return: (risk_level: 'safe'|'caution'|'danger', admin_required: bool)
    """
    if not cmd:
        return "safe", False
    s = cmd.lower()
    if any(re.search(p, s) for p in _DANGEROUS_PATTERNS):
        return "danger", True
    if any(re.search(p, s) for p in _CAUTION_PATTERNS):
        return "caution", True
    return "safe", False

def _prefer_ps_command(script_command: Optional[str], meta_admin_cmd: Optional[str]) -> Optional[str]:
    """
    CMD 전용(.cmd/.bat, cmd.exe, 'cmd /c') 냄새가 나면 숨기고,
    메타에 등록된 PowerShell 대안을 우선 사용한다.
    """
    if meta_admin_cmd:
        return meta_admin_cmd
    if not script_command:
        return None
    s = script_command.strip().lower()
    if s.endswith(".cmd") or s.endswith(".bat") or s.startswith("cmd ") or " cmd " in s or "cmd.exe" in s:
        return None
    return script_command

# ─────────────────────────────────────────────────────────────
# 휴리스틱 가이드 생성 (LLM 전 단계 초안)
# ─────────────────────────────────────────────────────────────
def build_human_guide(
    intent: str,
    shortcut: Optional[str],
    script_command: Optional[str],
) -> Tuple[str, str, bool]:
    """
    가이드 초안을 생성한다.
    return:
      - markdown 텍스트
      - risk_level('safe'|'caution'|'danger')
      - requires_confirmation(bool)
    """
    meta = UI_GUIDES.get(intent, {})
    meta_ui = meta.get("ui_path")
    meta_admin_required = bool(meta.get("admin_required", False))
    # 기본값 없이 받아서 아래에서 휴리스틱과 병합
    meta_risk = meta.get("risk_level")
    meta_notes = meta.get("notes")
    meta_admin_cmd = meta.get("admin_command")

    # cmd 기반 보조 판정
    risk_by_cmd, admin_by_cmd = _classify_risk_by_cmd(script_command or meta_admin_cmd)
    # 메타가 있으면 메타, 없으면 휴리스틱
    risk_level = meta_risk or risk_by_cmd
    admin_required = meta_admin_required or admin_by_cmd

    parts: list[str] = []

    # 1) 단축키가 있으면 최우선
    if shortcut:
        parts.append(f"가장 빠른 방법: **{shortcut}** 누르세요.")
        if meta_ui:
            parts.append(f"클릭 경로: {meta_ui}")

    # 2) 단축키 없고 (UI/명령) 중 하나라도 있으면 안내
    elif script_command or meta_admin_cmd or meta_ui:
        if meta_ui:
            parts.append(f"클릭 경로: {meta_ui}")
        # PS 대안 우선, CMD 냄새 나면 숨긴다
        cmd_text = _prefer_ps_command(script_command, meta_admin_cmd)
        if cmd_text:
            admin_label = "고급(관리자 권한 필요)" if admin_required else "고급"
            parts.append(f"{admin_label}: 아래 명령을 실행하세요.")
            parts.append("```powershell\n" + cmd_text + "\n```")

    # 3) 아무 것도 없으면 기본 문구
    else:
        parts.append("해당 기능의 안내를 준비 중입니다.")

    # 노트/경고
    if meta_notes:
        parts.append(f"ℹ️ 참고: {meta_notes}")

    requires_confirmation = (risk_level in ("caution", "danger"))
    if risk_level == "danger":
        parts.append("⚠️ 주의: 되돌릴 수 없는 변경이 발생할 수 있습니다.")
    elif risk_level == "caution":
        parts.append("⚠️ 주의: 시스템 설정에 영향을 줄 수 있으니 필요 시에만 사용하세요.")

    return ("\n\n".join(parts).strip(), risk_level, requires_confirmation)

# ─────────────────────────────────────────────────────────────
# LLM 보정 (말투 정리용). 실패 시 휴리스틱 결과 반환.
# ─────────────────────────────────────────────────────────────
async def generate_guide_response(
    message: str,
    intent: str,
    shortcut: Optional[str] = None,
    script_command: Optional[str] = None,
) -> str:
    """
    기존 시그니처 유지: str(Markdown)만 반환 → 기존 호출부 안 깨짐.
    내부에서 UI/위험도 휴리스틱을 적용한 뒤 LLM으로 말투만 다듬는다.
    """
    draft_md, _, _ = build_human_guide(intent, shortcut, script_command)

    system = (
        "역할: 당신은 Windows 사용자를 돕는 안내 비서입니다. 친절하게 대답해주세요\n"
        "원칙:\n"
        "1) UI 경로를 먼저, 단축키가 있으면 최상단에 강조.\n"
        "2) 명령은 '고급(관리자)' 섹션에서만 간결히. CMD 유도 금지, PowerShell 기준.\n"
        "3) 단계별, 공손, 과장 금지. 불확실한 정보는 만들지 말 것.\n"
        "출력: 한국어 Markdown, 불필요한 서론/결론 금지."
    )

    user_prompt = (
        f"기능: {intent}\n"
        f"사용자 요청: {message}\n\n"
        f"초안(다듬어 주세요):\n{draft_md}"
    )

    # OpenAI 키 없거나 호출 실패하면 초안 그대로 반환
    try:
        if not os.getenv("OPENAI_API_KEY"):
            return draft_md

        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user_prompt}],
            temperature=0.2,
        )
        content = (resp.choices[0].message.content or "").strip()
        return content or draft_md
    except Exception:
        return draft_md

# ─────────────────────────────────────────────────────────────
# 선택: 프론트에서 경고창 띄우고 싶을 때 쓰는 payload 버전
# ─────────────────────────────────────────────────────────────
async def generate_guide_payload(
    message: str,
    intent: str,
    shortcut: Optional[str] = None,
    script_command: Optional[str] = None,
) -> Dict[str, Any]:
    """
    텍스트 + 위험도/확인 필요 플래그를 함께 반환.
    """
    draft_md, risk_level, requires_confirmation = build_human_guide(intent, shortcut, script_command)
    text = await generate_guide_response(message, intent, shortcut, script_command)
    return {
        "ok": True,
        "message_markdown": text,
        "risk_level": risk_level,
        "requires_confirmation": requires_confirmation,
    }
