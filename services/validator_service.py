# validator_service.py
from typing import Dict

INTENT_REQUIRED_PARAMS = {
    "파일 삭제": ["file_path"],
    "파일 복사": ["source_path", "destination_path"]
}

def validate(intent: str, parameters: Dict[str, str]) -> Dict[str, any]:
    required_params = INTENT_REQUIRED_PARAMS.get(intent, [])
    missing = [p for p in required_params if p not in parameters]

    if missing:
        return {
            "valid": False,
            "missing_params": missing,
            "message": f"{intent} 실행 시 {', '.join(missing)} 정보가 필요합니다."
        }
    return {"valid": True, "missing_params": []} 