# api/v1/guide.py (신규 파일로 분리해도 되고, 기존 api_router에 바로 추가해도 됨)
from fastapi import APIRouter, HTTPException
from services.table_access import get_function_by_key
from services.ui_guide_service import build_ui_guide

router = APIRouter()

@router.get("/guide/{function_key}")
def get_guide(function_key: str):
    row = get_function_by_key(function_key)
    if not row:
        raise HTTPException(status_code=404, detail=f"Unknown function_key: {function_key}")
    return build_ui_guide(function_key, row)
