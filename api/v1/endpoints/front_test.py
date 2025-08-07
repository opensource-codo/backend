from typing import Dict
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from schemas.intent import UserRequest

router = APIRouter()

@router.post("/")
# async def search_intents(request: UserRequest):
async def search_intents(request: Request):
    data = await request.json()    
    return {
            "response" : "백엔드 테스트 "
    }