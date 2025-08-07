from typing import Dict
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from services.guide_service import generate_guide_response
from services.intent_service import extract_intent_with_rag, get_function_info, search_similar_intents
from services.validator_service import validate
from services.executor_service import execute_action
from schemas.intent import UserRequest, MethodName, IntentResponse

router = APIRouter()

@router.post("/", response_model=IntentResponse)
async def handle_user_input(request: UserRequest):
    # RAG를 사용하여 intent 추출
    intent_result = await extract_intent_with_rag(request.text)
    intent = intent_result.get("intent")
    similarity = intent_result.get("similarity", 0)
    method_used = intent_result.get("method", "unknown")

    function_info = await get_function_info(intent)
    function_id = function_info["function_id"]
    shortcut = function_info["shortcut"]

    parameters = {}

    if request.method == "GUIDE":
        # 가이드: OpenAI에 메시지를 넘겨 설명 받기
        guide_response = await generate_guide_response(request.text, intent, shortcut)
        return IntentResponse(
            intent=intent,
            method=request.method,
            parameters=parameters,
            status="guide_completed",
            message=guide_response
        )

    elif request.method == "EXECUTION":
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

@router.post("/search")
async def search_intents(request: UserRequest):
    """사용자 입력과 유사한 intent들을 검색합니다."""
    try:
        similar_intents = await search_similar_intents(request.text, n_results=5)
        
        return {
            "query": request.text,
            "results": similar_intents,
            "total_results": len(similar_intents)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"검색 중 오류가 발생했습니다: {str(e)}")

@router.post("/embed")
async def embed_database():
    """데이터베이스의 모든 데이터를 ChromaDB에 임베딩합니다."""
    try:
        from services.table_embedding import create_embedding_instance
        embedding_db = create_embedding_instance()
        
        return {
            "message": "데이터베이스 임베딩이 완료되었습니다.",
            "status": "success"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"임베딩 중 오류가 발생했습니다: {str(e)}")
    