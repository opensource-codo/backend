# api/v1/endpoints/user_input_re.py
from __future__ import annotations

from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.guide_service import generate_guide_response
from services.intent_service import extract_intent_with_rag, db_get_function_info, search_similar_intents
from services.validator_service import validate, validator_service, validate_text_parameters
from services.executor_service import plan_action
from services import interaction_store
from services.param_extractor import extract_params_llm
from services import table_access  # ← 추가: script_command/shortcut 폴백 조회

from schemas.intent import UserRequest, MethodName
from schemas.intent import IntentResponse  # 확장 IntentResponse

router = APIRouter()
SIM_THRESHOLD = 0.3  # 임베딩 수정 후 재조정 권장


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
    intent_result = await extract_intent_with_rag(request.text)
    intent = (intent_result.get("intent") or "").strip()
    similarity = float(intent_result.get("similarity", 0.0))
    method_used = intent_result.get("method", "unknown")

    if not intent:
        alts = await search_similar_intents(request.text, n_results=5)
        return IntentResponse(
            intent="",
            method=request.method,
            parameters={},
            status="no_intent",
            message="의도를 식별하지 못했어요.",
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
            message=f"의도 신뢰도가 낮아요({similarity:.2f}). 다시 입력해주세요.",
            similar_intents=alts,
            similarity=similarity,
            method_used=method_used,
        )

    # 2) 함수 메타
    fn = db_get_function_info(intent) or {}
    function_key = (fn.get("function_key") or "").strip()
    shortcut = fn.get("shortcut") or ""
    script_command = fn.get("script_command")  # ← 가이드 리스크/고급 섹션에 활용

    # 폴백: table_access에서 보완 정보 조회
    if not script_command or not shortcut:
        try:
            row = table_access.get_function_by_key(function_key or intent)
            if row:
                script_command = script_command or row.get("script_command")
                shortcut = shortcut or (row.get("shortcut") or "")
        except Exception:
            pass

    # function_key 누락 시 폴백(가능하면 공개 API로 대체 권장)
    if not function_key:
        try:
            function_key = validator_service._get_function_key_from_intent(intent)
        except Exception:
            function_key = ""

    # 3) GUIDE
    if request.method == MethodName.GUIDE:
        guide = await generate_guide_response(
            request.text,
            intent,
            shortcut,
            script_command,     # ← 추가
            show_commands=False # ← 기본은 초보자 모드
        )
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
    schema = validator_service.get_intent_params(intent)

    # function 매핑 누락
    if schema.get("not_configured"):
        return IntentResponse(
            intent=intent,
            method=request.method,
            parameters={},
            status="no_intent",
            message="구성되지 않은 의도입니다. 관리자에게 기능 매핑을 요청하세요.",
            similarity=similarity,
            method_used=method_used
        )

    if request.method == MethodName.EXECUTION:
        # 텍스트 추정값 + 규칙 기반 병합
        pre_params = extract_params_llm(intent, request.text, schema) or {}
        rb_params = validate_text_parameters(intent, request.text) or {}
        for k, v_ in rb_params.items():
            pre_params.setdefault(k, v_)
        v = validate(intent, pre_params, method=MethodName.EXECUTION, text=request.text)
    else:
        return IntentResponse(
            intent=intent,
            method=request.method,
            parameters={},
            status="unknown_method",
            message="지원되지 않는 method입니다.",
            similarity=similarity,
            method_used=method_used,
        )

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
    plan = await plan_action(function_key or intent, params, shortcut=shortcut)  # ← shortcut 전달

    if not plan.get("ok"):
        return IntentResponse(
            intent=intent,
            method=request.method,
            parameters=params,
            status="error",
            message=plan.get("message", "실행 계획 생성 실패"),
            shortcut=shortcut,
            similarity=similarity,
            method_used=method_used
        )

    return IntentResponse(
        intent=intent,
        method=request.method,
        parameters=params,
        status="ready_to_execute",
        message=plan.get("message"),
        shortcut=plan.get("shortcut") or shortcut,
        similarity=similarity,
        method_used=method_used,
        exec=plan.get("exec")
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
    v = validate(intent, parameters=merged, method=MethodName.EXECUTION, text=req.text or "")
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
    plan = await plan_action(function_key or intent, params, shortcut=shortcut)  # ← shortcut 전달

    interaction_store.delete(req.interaction_id)

    if not plan.get("ok"):
        return IntentResponse(
            intent=intent,
            method=req.method,
            parameters=params,
            status="error",
            message=plan.get("message", "실행 계획 생성 실패"),
            shortcut=shortcut,
            similarity=st["similarity"],
            method_used=st["method_used"],
        )

    return IntentResponse(
        intent=intent,
        method=req.method,
        parameters=params,
        status="ready_to_execute",
        message="실행 계획 생성",
        shortcut=plan.get("shortcut") or shortcut,
        similarity=st["similarity"],
        method_used=st["method_used"],
        exec=plan.get("exec")
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
            method=MethodName.EXECUTION,  # ← 고정 (ConfirmRequest엔 method 없음)
            parameters=params,
            status="cancelled",
            message="사용자 취소로 실행하지 않았습니다.",
            similarity=st["similarity"],
            method_used=st["method_used"],
            shortcut=shortcut,
        )

    # 승인 → 실행
    plan = await plan_action(function_key or intent, params, shortcut=shortcut)  # ← shortcut 전달
    interaction_store.delete(req.interaction_id)

    if not plan.get("ok"):
        return IntentResponse(
            intent=intent,
            method=MethodName.EXECUTION,  # ← 버그 픽스: req.method 사용 금지
            parameters=params,
            status="error",
            message=plan.get("message", "실행 계획 생성 실패"),
            shortcut=shortcut,
            similarity=st["similarity"],
            method_used=st["method_used"],
        )

    return IntentResponse(
        intent=intent,
        method=MethodName.EXECUTION,
        parameters=params,
        status="ready_to_execute",
        message="실행 계획 생성",
        shortcut=plan.get("shortcut") or shortcut,
        similarity=st["similarity"],
        method_used=st["method_used"],
        exec=plan.get("exec")
    )
