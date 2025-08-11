from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.guide_service import generate_guide_response
from services.intent_service import extract_intent_with_rag, db_get_function_info, search_similar_intents
from services.validator_service import validate, validator_service
from services.executor_service import execute_action
from services import interaction_store  # 새로 추가
from services.params_service import get_text_parameters

from schemas.intent import UserRequest, MethodName
from schemas.intent import IntentResponse  # 확장 IntentResponse (앞서 정의했던 버전)


router = APIRouter()
SIM_THRESHOLD = 0.75


# --- 새 요청 스키마 ---
class ContinueRequest(BaseModel):
    interaction_id: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    text: Optional[str] = None
    method: MethodName = MethodName.EXECUTION  # 보강도 EXECUTION 기준 검증


class ConfirmRequest(BaseModel):
    interaction_id: str
    confirm: bool = True


@router.post("/", response_model=IntentResponse)
async def handle_user_input(request: UserRequest):
    # 1) RAG로 intent 추출
    # TODO : intent 임시로
    # intent_result = await extract_intent_with_rag(request.text)
    # intent = (intent_result.get("intent") or "").strip()
    # similarity = float(intent_result.get("similarity", 0.0))
    # method_used = intent_result.get("method", "unknown")
    intent = "rename_file"
    similarity = 0.85
    method_used = "rag"

    if not intent:
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

    # 2) 함수 메타
    fn = await db_get_function_info(intent)  # 반드시 function_key를 포함하도록 구현 권장
    function_key = (fn.get("function_key") or "").strip()
    # shortcut = fn.get("shortcut") or ""
    # TODO : shortcut 임시로
    shortcut = "F12"
    if not function_key:
        # fallback: validator에서 조회(내부조인)
        try:
            function_key = validator_service._get_function_key_from_intent(intent)  # 내부함수이지만 실용적 폴백
        except Exception:
            function_key = ""

    # 3) GUIDE
    if request.method == "GUIDE":
        guide = await generate_guide_response(request.text, intent, shortcut)
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

    # 4) EXECUTION/SIMULATION (초판 검증)
    #    - 첫 호출에서 모든 정보를 받았을 수도 있음
    parameters = get_text_parameters(intent, request.text)
    v = validate(intent, parameters=request.parameters or {}, method=str(request.method), text=request.text)
    schema = validator_service.get_intent_params(intent)  # 파라미터 스키마(가이드용)

    # 부족 → 세션 생성 + info_required
    if not v["valid"]:
        iid = interaction_store.create(
            intent=intent,
            function_key=function_key,
            normalized_params=v.get("normalized_params", {}),
            missing_params=v.get("missing_params", []),
            schema=schema,
            shortcut=shortcut,
            similarity=similarity,
            method_used=method_used,
            requires_confirmation=False,
        )
        return IntentResponse(
            intent=intent,
            method=request.method,
            parameters=v.get("normalized_params", {}),
            status="info_required",
            missing_params=v.get("missing_params", []),
            parameter_schema=schema,
            message=v.get("message", "필요한 정보를 더 입력해주세요."),
            interaction_id=iid,
            similarity=similarity,
            method_used=method_used,
            shortcut=shortcut,
        )

    # 확인 필요 → 세션 생성 + confirm_required
    if v.get("requires_confirmation"):
        iid = interaction_store.create(
            intent=intent,
            function_key=function_key,
            normalized_params=v.get("normalized_params", {}),
            missing_params=[],
            schema=schema,
            shortcut=shortcut,
            similarity=similarity,
            method_used=method_used,
            requires_confirmation=True,
        )
        return IntentResponse(
            intent=intent,
            method=request.method,
            parameters=v.get("normalized_params", {}),
            status="confirm_required",
            message="이 작업은 위험할 수 있어요. 확인 후 다시 실행해주세요.",
            interaction_id=iid,
            similarity=similarity,
            method_used=method_used,
            shortcut=shortcut,
        )

    # 실행
    params = v.get("normalized_params", {})
    exec_result = await execute_action(function_key or intent, params)
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


# -------------------- 후속 요청: 파라미터 보강 --------------------
@router.post("/continue", response_model=IntentResponse)
async def continue_intent(req: ContinueRequest):
    st = interaction_store.get(req.interaction_id)
    if not st:
        raise HTTPException(status_code=404, detail="유효하지 않은 interaction_id 입니다. 시간이 만료되었을 수 있어요.")

    intent = st["intent"]
    function_key = st["function_key"]
    shortcut = st["shortcut"]
    # 누적 파라미터 병합
    merged = dict(st.get("normalized_params", {}))
    merged.update(req.parameters or {})

    # 재검증 (RAG 없음!)
    v = validate(intent, parameters=merged, method="EXECUTION", text=req.text or "")
    schema = st.get("schema") or validator_service.get_intent_params(intent)

    if not v["valid"]:
        interaction_store.update(
            req.interaction_id,
            normalized_params=v.get("normalized_params", {}),
            missing_params=v.get("missing_params", []),
            schema=schema,
            requires_confirmation=False,
        )
        return IntentResponse(
            intent=intent,
            method=req.method,
            parameters=v.get("normalized_params", {}),
            status="info_required",
            missing_params=v.get("missing_params", []),
            parameter_schema=schema,
            message=v.get("message", "아직 필요한 정보가 더 있어요."),
            interaction_id=req.interaction_id,
            similarity=st["similarity"],
            method_used=st["method_used"],
            shortcut=shortcut,
        )

    if v.get("requires_confirmation"):
        interaction_store.update(
            req.interaction_id,
            normalized_params=v.get("normalized_params", {}),
            missing_params=[],
            requires_confirmation=True,
        )
        return IntentResponse(
            intent=intent,
            method=req.method,
            parameters=v.get("normalized_params", {}),
            status="confirm_required",
            message="이 작업은 위험할 수 있어요. 확인 후 다시 실행해주세요.",
            interaction_id=req.interaction_id,
            similarity=st["similarity"],
            method_used=st["method_used"],
            shortcut=shortcut,
        )

    # 실행
    params = v.get("normalized_params", {})
    exec_result = await execute_action(function_key or intent, params)
    # 완료되었으니 세션 정리
    interaction_store.delete(req.interaction_id)
    return IntentResponse(
        intent=intent,
        method=req.method,
        parameters=params,
        status="executed",
        message=exec_result.get("message"),
        shortcut=exec_result.get("shortcut", shortcut),
        interaction_id=req.interaction_id,
        similarity=st["similarity"],
        method_used=st["method_used"],
    )


# -------------------- 최종 확인 --------------------
@router.post("/confirm", response_model=IntentResponse)
async def confirm_intent(req: ConfirmRequest):
    st = interaction_store.get(req.interaction_id)
    if not st:
        raise HTTPException(status_code=404, detail="유효하지 않은 interaction_id 입니다. 시간이 만료되었을 수 있어요.")

    intent = st["intent"]
    function_key = st["function_key"]
    shortcut = st["shortcut"]
    params = st.get("normalized_params", {})

    if not st.get("requires_confirmation"):
        raise HTTPException(status_code=400, detail="현재 흐름은 확인이 필요한 상태가 아닙니다.")

    if not req.confirm:
        interaction_store.delete(req.interaction_id)
        return IntentResponse(
            intent=intent,
            method=MethodName.EXECUTION,
            parameters=params,
            status="cancelled",
            message="사용자 취소로 실행하지 않았습니다.",
            interaction_id=req.interaction_id,
            similarity=st["similarity"],
            method_used=st["method_used"],
            shortcut=shortcut,
        )

    # 승인 → 실행
    exec_result = await execute_action(function_key or intent, params)
    interaction_store.delete(req.interaction_id)
    return IntentResponse(
        intent=intent,
        method=MethodName.EXECUTION,
        parameters=params,
        status="executed",
        message=exec_result.get("message"),
        shortcut=exec_result.get("shortcut", shortcut),
        interaction_id=req.interaction_id,
        similarity=st["similarity"],
        method_used=st["method_used"],
    )
