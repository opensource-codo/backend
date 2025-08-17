from fastapi import FastAPI

from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import subprocess

# FastAPI 앱 생성
app = FastAPI()


# ✅ 클라이언트 요청 바디 구조 정의
class UserInputRequest(BaseModel):
    text: str   # 사용자가 입력한 메시지 (예: "파일 복사")
    method: str # 실행 방법 (예: EXECUTION, GUIDE)

# ✅ 서버 응답 바디 구조 정의 (명세서 기반)
class UserInputResponse(BaseModel):
    intent: str               # 분석된 의도 (예: "파일 복사")
    method: str               # 실행 방법
    parameters: Dict[str, Any]# intent 실행에 필요한 파라미터들
    status: str               # 상태 (executed | error | unknown_method 등)
    message: str              # 결과 메시지
    missing_params: Optional[List[str]] # 누락된 파라미터 목록
    parameter_schema: Dict[str, Any]    # 요청에 필요한 파라미터 스키마
    interaction_id: Optional[str]       # 상호작용 ID (추적용)
    similarity: Optional[float]         # 유사도 점수 (AI intent 매칭)
    method_used: Optional[str]          # 어떤 방식으로 intent를 추출했는지
    shortcut: Optional[str]             # 단축 명령어 여부

# ✅ 특정 intent와 스크립트 파일 매핑
SCRIPTS_MAP = {
    "볼륨 높이기": "volume_up.py",#
    "볼륨 줄이기": "volume_down.py",#
    "음소거 토글": "mute_toggle.py",#
    "휴지통 비우기": "empty_recycle_bin.py",#
    "블루투스 켜기": "toggle_bluetooth_on.py",#
    "블루투스 끄기": "toggle_bluetooth_off.py",#
    "밝기 높이기": "adjust_brightness_up.py",#
    "밝기 줄이기": "adjust_brightness_down.py",
    "윈도우 업데이트 확인": "check_update.py",
    "브라우저 정리": "clear_browser_data.py",#check
    "작업 관리자 열기": "open_taskmgr.py",
    "화면 캡처하기": "screenshot.py",
    "화면 잠금": "lock_screen.py",
    "명령 프롬프트 열기": "open_cmd.py",
    "제어판 열기": "open_control_panel.py",
    "휴지통 비우기": "empty_recycle_bin.py",
    "화면 확대": "zoom_in.py",
    "화면 축소": "zoom_out.py",
    "파일 찾기": "search_file.py",
    "메모장 열기": "open_notepad.py",
    "설정 열기": "open_settings.py",
    "파일 복사": "file_copy_paste.py",
    "파일 잘라내기": "file_cut.py",
    "파일 삭제": "file_delete.py",
}

# ✅ intent 추출 함수 (추후 AI 모델 연결 가능)
def extract_intent(text: str) -> str:
    # 입력된 text에 intent 키워드가 포함되어 있으면 해당 intent 반환
    for intent in SCRIPTS_MAP.keys():
        if intent in text:
            return intent
    # 일치하는 intent가 없을 경우 "unknown" 반환
    return "unknown"

# ✅ 사용자 입력 API
@app.post("/api/v1/userinput", response_model=UserInputResponse)
async def exec_userinput(body: UserInputRequest):

    # (1) 입력된 문장에서 intent 추출
    intent = extract_intent(body.text)

    # (2) intent가 인식되면 similarity=1.0, 없으면 0.0 처리
    similarity = 1.0 if intent != "unknown" else 0.0

    # (3) interaction_id는 추적용 (고정값 예시)
    interaction_id = "abc123"
    shortcut = None

    # (4) 파라미터 스키마 (명세서에 맞춤)
    parameter_schema = {
        "required": [{"name": "src_path", "type": "path"}], 
        "optional": [{"name": "force", "type": "bool", "default": False}]
    }

    # (5) 지원하지 않는 method일 경우 오류 반환
    if body.method not in ["EXECUTION", "GUIDE", "SIMULATION"]:
        return UserInputResponse(
            intent=intent,
            method=body.method,
            parameters={},
            status="unknown_method",
            message="지원하지 않는 method입니다.",  # 에러 메시지
            missing_params=[],
            parameter_schema=parameter_schema,
            interaction_id=interaction_id,
            similarity=similarity,
            method_used="llm",
            shortcut=shortcut
        )

    # (6) intent가 없을 경우 no_intent 상태 반환
    if intent == "unknown":
        return UserInputResponse(
            intent=intent,
            method=body.method,
            parameters={},
            status="no_intent",
            message="알맞은 intent를 찾을 수 없습니다.",
            missing_params=[],
            parameter_schema=parameter_schema,
            interaction_id=interaction_id,
            similarity=similarity,
            method_used="llm",
            shortcut=shortcut
        )

    # (7) intent에 맞는 스크립트 경로 추출
    script_path = SCRIPTS_MAP[intent]

    # (8) 실제 스크립트 실행 (python 파일 실행)
    try:
        # subprocess로 외부 파이썬 스크립트 실행 후 결과 받음
        result = subprocess.check_output(
            f'python {script_path}', shell=True, text=True
        )
        status = "executed"         # 성공 상태
        message = result.strip()    # 실행 결과 메시지
    except Exception as e:
        status = "error"            # 오류 상태
        message = str(e)            # 에러 메시지

    # (9) 최종 응답 반환
    return UserInputResponse(
        intent=intent,
        method=body.method,
        parameters={},      # 현재는 빈 값 (추후 확장 가능)
        status=status,      # 실행 성공/실패 상태
        message=message,    # 실행된 메시지
        missing_params=[],  # 파라미터 누락 여부 (추후 확장 가능)
        parameter_schema=parameter_schema,
        interaction_id=interaction_id,
        similarity=similarity,
        method_used="llm",  # AI/LLM 사용 표시
        shortcut=shortcut
    )
