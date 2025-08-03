from typing import Dict
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from services.guide_service import generate_guide_response
from services.intent_service import extract_intent, get_function_info
from services.validator_service import validate
from services.executor_service import execute_action
from schemas.intent import UserRequest, MethodName, IntentResponse

router = APIRouter()

@router.post("/userInput", response_model=IntentResponse)
async def handle_user_input(request: UserRequest):
    # TODO : shortcut 추출 필요, generate_guide_response
    intent_result = await extract_intent(request.text)
    intent = intent_result.get("intent")

    function_info = await get_function_info(intent)
    function_id = function_info["function_id"]
    shortcut = function_info["shortcut"]

    parameters = {}

    if request.method == "guide":
        # 가이드: OpenAI에 메시지를 넘겨 설명 받기
        guide_response = await generate_guide_response(request.text, intent, shortcut)
        return IntentResponse(
            intent=intent,
            method=request.method,
            parameters=parameters,
            status="guide_completed",
            message=guide_response
        )

    elif request.method == "execution":
        # 파라미터 검증
        validation_result = validate(intent, parameters)
        if not validation_result["valid"]:
            return IntentResponse(
                intent=intent,
                method=request.method,
                parameters=parameters,
                status="info_required",
                missing_params=validation_result.get("missing_params", []),
                message="필요한 정보를 더 입력해주세요."
            )

        # action executor 호출
        exec_result = execute_action(intent, parameters)
        return IntentResponse(
            intent=intent,
            method=request.method,
            parameters=parameters,
            status="executed",
            message=exec_result.get("message"),
            shortcut=exec_result.get("shortcut")
        )

    else:
        return IntentResponse(
            intent=intent,
            method=request.method,
            parameters=parameters,
            status="unknown_method",
            message="지원되지 않는 method입니다."
        )
    