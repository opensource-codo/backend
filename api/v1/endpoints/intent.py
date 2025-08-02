from typing import Dict
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from services.intent_service import extract_intent
from services.validator_service import validate
from schemas.intent import IntentRequest, ValidateRequest

router = APIRouter()

@router.post("/")
async def get_intent(request: IntentRequest):
    intent_result = await extract_intent(request.text)
    return intent_result

@router.post("/validate")
async def validate_parameters(request: ValidateRequest):
    result = validate(request.intent, request.parameters)
    return result
