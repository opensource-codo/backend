# endpoints/guide.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.guide_service import generate_guide_response
from schemas.guide import GuideRequest

router = APIRouter()

@router.post("/")
async def guide_user(req: GuideRequest):
    try:
        result = await generate_guide_response(req.text, req.intent, req.shortcut)
        return {"response": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
