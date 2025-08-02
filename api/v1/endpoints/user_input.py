from typing import Dict
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from services.guide_service import get_openai_response
from schemas.intent import UserRequest, MethodName

router = APIRouter()

@router.post("/")
async def get_intent(request: UserRequest):
    message = request.text
    method = request.method

    if method is MethodName.guide:
        guide_result = await get_openai_response(message)
        return guide_result
    
    if method is MethodName.execution:
        return True
    
    if method is MethodName.simulation:
        return True
    