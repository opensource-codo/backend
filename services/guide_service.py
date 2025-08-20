# services/guide_service.py
from __future__ import annotations

import os
import re
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ─────────────────────────────────────────────────────────────
# UI/명령어 매핑 메타 (빠른 운영용; 나중에 DB로 이관 가능)
# ─────────────────────────────────────────────────────────────
UI_GUIDES: Dict[str, Dict[str, Any]] = {
    "open_control_panel": {
        "ui_path": "Win + R → 'control' 입력 → 엔터",
        "shortcut": "Win + R → control",
        "admin_required": False,
        "risk_level": "safe",
    },
    "system_info": {
        "ui_path": "Win + Pause/Break",
        "shortcut": "Win + Pause/Break",
        "admin_required": False,
        "risk_level": "safe",
    },
    "device_manager": {
        "ui_path": "시작 버튼 우클릭 → '장치 관리자'",
        "shortcut": "Win + X → M",
        "admin_required": True,
        "risk_level": "caution",
        "notes": "드라이버 설치/삭제 작업은 시스템에 영향을 줄 수 있습니다.",
        "admin_command": "devmgmt.msc",
    },
    "network_adapter_reset": {
        "ui_path": "제어판 → 네트워크 및 공유 센터 → 어댑터 설정 변경 → 어댑터 우클릭 → '사용 안 함' 후 다시 '사용'",
        "admin_required": True,
        "risk_level": "caution",
        "notes": "네트워크 연결이 일시적으로 끊깁니다.",
        "admin_command": "Disable-NetAdapter -Name '이더넷' -Confirm:$false; Enable-NetAdapter -Name '이더넷' -Confirm:$false",
    },
    "windows_update": {
        "ui_path": "설정 → 업데이트 및 보안 → Windows 업데이트 → '업데이트 확인'",
        "admin_required": True,
        "risk_level": "safe",
        "notes": "업데이트 후 재부팅이 필요할 수 있습니다.",
        "admin_command": "UsoClient StartScan",
    },
    "shutdown_restart": {
        "ui_path": "시작 메뉴 → 전원 → 다시 시작",
        "shortcut": "Alt + F4 (바탕화면에서) → '다시 시작' 선택",
        "admin_required": True,
        "risk_level": "danger",
        "notes": "작업 중인 데이터는 반드시 저장해야 합니다.",
        "admin_command": "shutdown /r /t 0",
    },
    
    "open_taskmgr": {
        "ui_path": "작업 표시줄을 우클릭 → '작업 관리자' 클릭",
        "shortcut": "Ctrl + Shift + Esc",
        "admin_required": False,
        "risk_level": "safe",
    },
    "empty_recycle_bin": {
        "ui_path": "바탕화면 '휴지통' 아이콘 우클릭 → '휴지통 비우기'",
        "admin_required": False,
        "risk_level": "danger",
        "notes": "삭제 후 복구가 어렵습니다.",
        # PowerShell 순정 cmdlet만 표기
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
    명령 문자열 기반 위험도 및 관리자 권한 필요 여부 추정.
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
    CMD 전용(.cmd/.bat, cmd.exe, 'cmd /c') 패턴이 나오면 숨기고,
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
# 출력 페이로드 모델
# ─────────────────────────────────────────────────────────────
@dataclass
class GuidePayload:
    ok: bool
    # 최종 사용자용 메시지(초보자 모드 기준 – 클릭/단축키만)
    message_markdown: str
    # '고급' 버튼을 보여줄지 여부(명령 존재 여부)
    has_advanced: bool
    # 고급(명령) 섹션 마크다운 (show_commands=True일 때만 세팅)
    advanced_markdown: Optional[str]
    # 위험도 및 확인 필요 플래그(프론트에서 모달 제어)
    risk_level: str  # 'safe'|'caution'|'danger'
    requires_confirmation: bool

# ─────────────────────────────────────────────────────────────
# 휴리스틱 가이드(초안)
# ─────────────────────────────────────────────────────────────
def build_human_guide_core(
    intent: str,
    shortcut: Optional[str],
    script_command: Optional[str],
) -> Tuple[str, Optional[str], str, bool, bool]:
    """
    코어 초안 생성.
    return:
      - basic_md (초보자용: 클릭/단축키만)
      - advanced_md (고급 명령어 섹션; 없을 수 있음)
      - risk_level
      - requires_confirmation
      - has_advanced (명령 섹션 존재 여부)
    """
    meta = UI_GUIDES.get(intent, {})
    meta_ui = meta.get("ui_path")
    meta_admin_required = bool(meta.get("admin_required", False))
    meta_risk = meta.get("risk_level")
    meta_notes = meta.get("notes")
    meta_admin_cmd = meta.get("admin_command")
    meta_shortcut = shortcut or meta.get("shortcut")

    # cmd 기반 보조 판정
    risk_by_cmd, admin_by_cmd = _classify_risk_by_cmd(script_command or meta_admin_cmd)
    risk_level = meta_risk or risk_by_cmd
    admin_required = meta_admin_required or admin_by_cmd

    # PowerShell만 허용
    ps_cmd = _prefer_ps_command(script_command, meta_admin_cmd)

    # ── 기본(초보자) 섹션: 클릭/단축키만 ──
    basic_parts: list[str] = []
    # 헤더 문구(요구사항 반영)
    basic_parts.append("**가장 쉬운 방법: 클릭만 안내**")

    if meta_shortcut:
        basic_parts.append(f"- 단축키: **{meta_shortcut}**")

    if meta_ui:
        basic_parts.append(f"- 클릭 경로: {meta_ui}")

    if meta_notes:
        basic_parts.append(f"ℹ️ 참고: {meta_notes}")

    if risk_level == "danger":
        basic_parts.append("⚠️ 주의: 되돌릴 수 없는 변경이 발생할 수 있습니다.")
    elif risk_level == "caution":
        basic_parts.append("⚠️ 주의: 시스템 설정에 영향을 줄 수 있으니 필요 시에만 사용하세요.")

    basic_md = "\n".join(basic_parts).strip()

    # ── 고급(명령) 섹션 ──
    has_advanced = bool(ps_cmd)
    advanced_md = None
    if has_advanced:
        label = "고급(관리자 권한 필요)" if admin_required else "고급"
        adv_parts = [
            f"**{label}: 아래 명령어 보기**  \n(초보자는 이 단계를 건너뛰어도 됩니다.)",
            "```powershell",
            ps_cmd,
            "```",
        ]
        advanced_md = "\n".join(adv_parts)

    requires_confirmation = (risk_level in ("caution", "danger"))
    return basic_md, advanced_md, risk_level, requires_confirmation, has_advanced

# ─────────────────────────────────────────────────────────────
# LLM 보정 (말투 정리). 실패 시 휴리스틱 결과 사용.
# 
async def _polish_markdown_with_llm(draft_md: str, intent: str, message: str) -> str:
    system = (
        "역할: 당신은 Windows 사용자를 돕는 안내 비서입니다. 친절하고 간결하게 대답하세요.\n"
        "원칙:\n"
        "1) 초보자 우선. 클릭 경로/단축키만 보여주고, 명령은 언급하지 말 것.\n"
        "2) 단계를 짧고 명확히. 불필요한 서론 금지.\n"
        "3) 경고/참고는 간단한 이모지로 안내.\n"
        "출력: 한국어 Markdown."
    )
    user_prompt = f"기능: {intent}\n사용자 요청: {message}\n초안:\n{draft_md}"
    try:
        if not os.getenv("OPENAI_API_KEY"):
            return draft_md
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        content = (resp.choices[0].message.content or "").strip()
        return content or draft_md
    except Exception:
        return draft_md

# ─────────────────────────────────────────────────────────────
# 외부 API에서 쓰는 진입점들
# ─────────────────────────────────────────────────────────────
async def generate_guide_response(
    message: str,
    intent: str,
    shortcut: Optional[str] = None,
    script_command: Optional[str] = None,
    *,
    show_commands: bool = False,  # ← 기본값: 초보자 모드(명령 숨김)
) -> str:
    """
    (하위 호환) 문자열만 반환. show_commands=False이면 초보자용만.
    """
    basic_md, advanced_md, _, _, has_advanced = build_human_guide_core(
        intent, shortcut, script_command
    )
    # 초보자용 출력 LLM 다듬기
    basic_md = await _polish_markdown_with_llm(basic_md, intent, message)

    if show_commands and advanced_md:
        # 요구사항 문구 반영
        header = (
            "**가장 쉬운 방법: 클릭만 안내**\n\n"
            "필요하면 아래 **‘고급’** 버튼을 눌러 명령어를 확인하세요."
        )
        return f"{header}\n\n{basic_md}\n\n---\n\n{advanced_md}"

    # 기본은 명령 숨김
    footer_hint = "\n\n_필요하면 아래 ‘고급’ 버튼을 눌러 명령어 보기_." if has_advanced else ""
    return f"{basic_md}{footer_hint}"

async def generate_guide_payload(
    message: str,
    intent: str,
    shortcut: Optional[str] = None,
    script_command: Optional[str] = None,
    *,
    show_commands: bool = False,  # ← 기본값: 초보자 모드
) -> Dict[str, Any]:
    """
    텍스트 + 위험도/확인 필요 플래그 + 고급 섹션 유무를 함께 반환.
    프론트에서:
      - 항상 basic message를 먼저 보여주고
      - has_advanced=True면 '고급' 토글 버튼 노출
      - show_commands=True일 때만 advanced_markdown 렌더
      - danger/caution이면 requires_confirmation에 따라 확인 모달 표시
    """
    basic_md, advanced_md, risk_level, requires_confirmation, has_advanced = build_human_guide_core(
        intent, shortcut, script_command
    )
    # 초보자용 문구 LLM 다듬기
    basic_md = await _polish_markdown_with_llm(basic_md, intent, message)

    # 최종 사용자 표현 스펙 반영
    header = "**가장 쉬운 방법: 클릭만 안내**\n\n"
    hint = "\n\n_필요하면 아래 ‘고급’ 버튼을 눌러 명령어 보기_." if has_advanced else ""
    message_markdown = header + basic_md + hint

    payload = GuidePayload(
        ok=True,
        message_markdown=message_markdown,
        has_advanced=has_advanced,
        advanced_markdown=advanced_md if show_commands and advanced_md else None,
        risk_level=risk_level,
        requires_confirmation=requires_confirmation,
    )
    return payload.__dict__
