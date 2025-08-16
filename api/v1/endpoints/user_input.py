from typing import Dict
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from services.guide_service import generate_guide_response
from services.intent_service import extract_intent_with_rag, search_similar_intents
from services.params_service import get_function_info
from services.validator_service import validate
from services.executor_service import execute_action
from schemas.intent import UserRequest, MethodName, IntentResponse

router = APIRouter()
SIM_THRESHOLD = 0.75

# TODO : 세션화 + 후속 엔드포인트(/continue, /confirm, /cancel) 방식 변경
# 방식: 첫 호출에서 intent를 확정하고 interaction_id 발급.
# 이후 POST /continue는 intent 재탐색 없이 부족 파라미터만 보강/검증.
# POST /confirm은 위험 작업 승인만 처리.

@router.post("/", response_model=IntentResponse)
async def handle_user_input(request: UserRequest):
    # RAG를 사용하여 intent 추출
    intent_result = await extract_intent_with_rag(request.text)
    intent = (intent_result.get("intent") or "").strip()
    similarity = float(intent_result.get("similarity", 0.0))
    method_used = intent_result.get("method", "unknown")

    if not intent:
        # 유사 intent 제안
        alts = await search_similar_intents(request.text, n_results=5)
        return IntentResponse(
            intent="",
            method=request.method,
            parameters={},
            status="no_intent",
            message="의도를 식별하지 못했어요. 아래 후보를 참고해 주세요.",
            similar_intents=alts,  
            similarity=similarity,
            method_used=method_used,
        )

    if similarity < SIM_THRESHOLD:
            alts = await search_similar_intents(request.text, n_results=5)
            return IntentResponse(
                intent=intent,
                method=request.method,
                parameters={},
                status="low_confidence",
                message=f"의도 신뢰도가 낮아요({similarity:.2f}). 아래 후보 중에서 선택해 주세요.",
                similar_intents=alts,
                similarity=similarity,
                method_used=method_used,
            )
            
    function_info = await get_function_info(intent)
    function_id = function_info.get("function_id") or ""
    shortcut = function_info.get("shortcut") or ""

    parameters = {}

    if request.method == "GUIDE":
        # 가이드: OpenAI에 메시지를 넘겨 설명 받기
        guide = await generate_guide_response(request.text, intent, shortcut)
        # TODO : IntentResponse 수정 필요
        return IntentResponse(
            intent=intent,
            method=request.method,
            parameters={},
            status="guide_completed",
            message=guide,
            shortcut=shortcut,
            similarity=similarity,
            method_used=method_used,
        )


    if request.method == "EXECUTION":
        v = validate(intent, parameters=request.parameters or {}, method="EXECUTION", text=request.text)

        if not v["valid"]:
            return IntentResponse(
                intent=intent,
                method=request.method,
                parameters=v.get("normalized_params", {}),
                status="info_required",
                missing_params=v.get("missing_params", []),
                message=v.get("message", "필요한 정보를 더 입력해주세요."),
                similarity=similarity,
                method_used=method_used,
                shortcut=shortcut,
            )

        # 위험 작업이면 먼저 확인부터 요청
        if v.get("requires_confirmation"):
            return IntentResponse(
                intent=intent,
                method=request.method,
                parameters=v.get("normalized_params", {}),
                status="confirm_required",
                message="이 작업은 위험할 수 있어요. 확인 후 다시 실행해주세요.",
                similarity=similarity,
                method_used=method_used,
                shortcut=shortcut,
            )

        # 정상 실행: 반드시 '정규화된 파라미터'로 실행!
        params = v.get("normalized_params", {})
        exec_result = await execute_action(intent, params)  # 비동기라면 await로 변경

        return IntentResponse(
            intent=intent,
            method=request.method,
            parameters=params,
            status="executed",
            message=exec_result.get("message"),
            shortcut=exec_result.get("shortcut", shortcut),
            similarity=similarity,
            method_used=method_used,
        )
    
    return IntentResponse(
            intent=intent,
            method=request.method,
            parameters={},
            status="unknown_method",
            message="지원되지 않는 method입니다.",
            similarity=similarity,
            method_used=method_used,
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
    