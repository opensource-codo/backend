from typing import Dict
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from services.guide_service import createAiResponse
from schemas.intent import UserRequest, MethodName

router = APIRouter()

@router.post("/")
async def get_intent(request: UserRequest):
    text = request.text
    method = request.method

    if method is MethodName.guide:
        await createAiResponse(text)
    
    if method is MethodName.execution:
        return True
    
    if method is MethodName.simulation:
        return True
    