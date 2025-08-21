# api/v1/endpoints/user_input_re.py
from __future__ import annotations

from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services.guide_service import generate_guide_response
from services.intent_service import extract_intent_with_rag, db_get_function_info, search_similar_intents
from services.validator_service import validate, validator_service, validate_text_parameters
from services.executor_service import plan_action
from services import interaction_store
from services.param_extractor import extract_params_llm
from services import table_access  # script_command/shortcut 폴백 조회가 필요하면 사용

from schemas.intent import UserRequest, MethodName
from schemas.intent import IntentResponse  # 확장 IntentResponse

# ─────────────────────────────────────────────
# Logging 설정
# ─────────────────────────────────────────────
import os, json, logging
router = APIRouter()
SIM_THRESHOLD = 0.2  # 임베딩 수정 후 재조정 권장

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
logger = logging.getLogger("codo.user_input")
if not logger.handlers:
    # 파일 핸들러
    fh = logging.FileHandler(os.path.join(LOG_DIR, "user_input.log"), encoding="utf-8")
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    # 콘솔 핸들러(uvicorn 콘솔에도 노출)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    logger.setLevel(logging.INFO)


# --- 새 요청 스키마 ---
class ContinueRequest(BaseModel):
    interaction_id: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    text: Optional[str] = None
    method: MethodName = MethodName.EXECUTION  # 보강도 EXECUTION 기준 검증


class ConfirmRequest(BaseModel):
    interaction_id: str
    confirm: bool = True


def _mth(v) -> str:
    """MethodName enum/str -> 대문자 문자열"""
    if hasattr(v, "value"):
        return str(v.value).upper()
    return str(v).upper()


def _json(o) -> str:
    """ensure_ascii=False 로 한글이 깨지지 않게 JSON 직렬화"""
    try:
        return json.dumps(o, ensure_ascii=False)
    except Exception:
        return str(o)


def _client(req: Request) -> str:
    return getattr(req.client, "host", "?") if req and req.client else "?"


@router.post("/", response_model=IntentResponse)
async def handle_user_input(payload: UserRequest, req: Request):
    # 원문 요청 로깅
    base_log = {
        "event": "handle_user_input",
        "route": "/api/v1/userInputRe/",
        "remote": _client(req),
        "body": {
            "text": getattr(payload, "text", None),
            "method": _mth(getattr(payload, "method", None)),
            "parameters": getattr(payload, "parameters", {}) or {},
            "interaction_id": getattr(payload, "interaction_id", None),
        },
    }
    logger.info(_json(base_log))

    # 1) RAG로 intent 추출
    intent_result = await extract_intent_with_rag(payload.text)
    intent = (intent_result.get("intent") or "").strip()
    similarity = float(intent_result.get("similarity", 0.0))
    method_used = intent_result.get("method", "unknown")
    function_key_from_rag = (intent_result.get("function_key") or "").strip()

    # (A) intent가 비었으면: 별칭/폴백으로 function_key 추정
    alias_fk: Optional[str] = None
    if not intent:
        try:
            alias_fk = validator_service._get_function_key_from_intent(payload.text or "")
        except Exception:
            alias_fk = None
        if alias_fk:
            # intent 문자열은 사용자 원문을 유지(스키마는 function_key로 가져옴)
            intent = (payload.text or alias_fk).strip()
            function_key_from_rag = function_key_from_rag or alias_fk
            method_used = f"{method_used}+alias_fallback" if method_used else "alias_fallback"
            similarity = max(similarity, 0.99)  # 유사도 임계 우회

    # (B) intent가 끝내 비면 no_intent
    if not intent:
        alts = await search_similar_intents(payload.text, n_results=5)
        out = IntentResponse(
            intent="",
            method=payload.method,
            parameters={},
            status="no_intent",
            message="의도를 식별하지 못했어요.",
            similar_intents=alts,
            similarity=similarity,
            method_used=method_used,
        )
        logger.info(_json({
            "event": "handle_user_input.end",
            "status": out.status,
            "intent": out.intent,
            "similarity": out.similarity,
            "method_used": out.method_used,
        }))
        return out

    # 2) function_key/shortcut 조회
    if function_key_from_rag:
        function_key = function_key_from_rag
        # intent로 못 찾으면 function_key로도 조회
        fn = db_get_function_info(intent) or db_get_function_info(function_key_from_rag) or {}
        shortcut = fn.get("shortcut", "")
    else:
        fn = db_get_function_info(intent) or {}
        function_key = (fn.get("function_key") or "").strip()
        shortcut = fn.get("shortcut") or ""
        # fallback: validator에서 조회
        if not function_key:
            try:
                function_key = validator_service._get_function_key_from_intent(intent) or ""
            except Exception:
                function_key = ""

    # 3) GUIDE
    if payload.method == MethodName.GUIDE:
        guide = await generate_guide_response(payload.text, intent, shortcut)
        out = IntentResponse(
            intent=intent,
            method=payload.method,
            parameters={},
            status="guide_completed",
            message=guide,
            shortcut=shortcut,
            similarity=similarity,
            method_used=method_used,
        )
        logger.info(_json({
            "event": "handle_user_input.end",
            "status": out.status,
            "intent": out.intent,
            "similarity": out.similarity,
            "method_used": out.method_used,
            "shortcut": out.shortcut,
        }))
        return out

    # 4) EXECUTION 검증
    schema = validator_service.get_intent_params(intent)

    # function 매핑 누락
    if schema.get("not_configured"):
        out = IntentResponse(
            intent=intent,
            method=payload.method,
            parameters={},
            status="no_intent",
            message="구성되지 않은 의도입니다. 관리자에게 기능 매핑을 요청하세요.",
            similarity=similarity,
            method_used=method_used
        )
        logger.info(_json({
            "event": "handle_user_input.end",
            "status": out.status,
            "intent": out.intent,
            "message": out.message,
        }))
        return out

    # 유사도 낮음 처리(단, 별칭/폴백으로 function_key가 잡혀 있으면 통과)
    if similarity < SIM_THRESHOLD and not function_key_from_rag and not function_key:
        alts = await search_similar_intents(payload.text, n_results=5)
        out = IntentResponse(
            intent=intent,
            method=payload.method,
            parameters={},
            status="low_confidence",
            message=f"의도 신뢰도가 낮아요({similarity:.2f}). 다시 입력해주세요.",
            similar_intents=alts,
            similarity=similarity,
            method_used=method_used,
        )
        logger.info(_json({
            "event": "handle_user_input.end",
            "status": out.status,
            "intent": out.intent,
            "similarity": out.similarity,
        }))
        return out

    if payload.method == MethodName.EXECUTION:
        # 텍스트 추정값 + 규칙 기반 병합
        pre_params = extract_params_llm(intent, payload.text, schema) or {}
        v = validate(intent, pre_params, text=payload.text, method=_mth(payload.method))
    else:
        out = IntentResponse(
            intent=intent,
            method=payload.method,
            parameters={},
            status="unknown_method",
            message="지원되지 않는 method입니다.",
            similarity=similarity,
            method_used=method_used,
        )
        logger.info(_json({
            "event": "handle_user_input.end",
            "status": out.status,
            "intent": out.intent,
        }))
        return out

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
        out = IntentResponse(
            intent=intent,
            method=payload.method,
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
        logger.info(_json({
            "event": "handle_user_input.end",
            "status": out.status,
            "intent": out.intent,
            "interaction_id": out.interaction_id,
            "missing_params": out.missing_params,
        }))
        return out

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
        out = IntentResponse(
            intent=intent,
            method=payload.method,
            parameters=v.get("normalized_params", {}),
            status="confirm_required",
            message="이 작업은 위험할 수 있어요. 확인 후 다시 실행해주세요.",
            interaction_id=iid,
            similarity=similarity,
            method_used=method_used,
            shortcut=shortcut,
        )
        logger.info(_json({
            "event": "handle_user_input.end",
            "status": out.status,
            "intent": out.intent,
            "interaction_id": out.interaction_id,
        }))
        return out

    # 5) 실행 계획 생성(위험 작업이 아닌 경우)
    params = v.get("normalized_params", {})
    plan = await plan_action(function_key or intent, params, shortcut=shortcut)  # ← shortcut 전달

    if not plan.get("ok"):
        out = IntentResponse(
            intent=intent,
            method=payload.method,
            parameters=params,
            status="error",
            message=plan.get("message", "실행 계획 생성 실패"),
            shortcut=shortcut,
            similarity=similarity,
            method_used=method_used
        )
        logger.info(_json({
            "event": "handle_user_input.end",
            "status": out.status,
            "intent": out.intent,
            "message": out.message,
        }))
        return out

    out = IntentResponse(
        intent=intent,
        method=payload.method,
        parameters=params,
        status="ready_to_execute",
        message=plan.get("message"),
        shortcut=plan.get("shortcut") or shortcut,
        similarity=similarity,
        method_used=method_used,
        exec=plan.get("exec")
    )
    logger.info(_json({
        "event": "handle_user_input.end",
        "status": out.status,
        "intent": out.intent,
        "exec_kind": (out.exec or {}).get("kind") if isinstance(out.exec, dict) else None,
    }))
    return out


# -------------------- 후속 요청: 파라미터 보강 --------------------
@router.post("/continue", response_model=IntentResponse)
async def continue_intent(req: ContinueRequest, raw: Request):
    logger.info(_json({
        "event": "continue_intent",
        "route": "/api/v1/userInputRe/continue",
        "remote": _client(raw),
        "body": {
            "interaction_id": req.interaction_id,
            "method": _mth(req.method),
            "parameters": req.parameters or {},
        }
    }))

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
    v = validate(intent, parameters=merged, text=req.text or "", method=_mth(req.method))
    schema = st.get("schema") or validator_service.get_intent_params(intent)

    if not v["valid"]:
        interaction_store.update(
            req.interaction_id,
            normalized_params=v.get("normalized_params", {}),
            missing_params=v.get("missing_params", []),
            schema=schema,
            requires_confirmation=False,
        )
        out = IntentResponse(
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
        logger.info(_json({
            "event": "continue_intent.end",
            "status": out.status,
            "intent": out.intent,
            "interaction_id": out.interaction_id,
            "missing_params": out.missing_params,
        }))
        return out

    if v.get("requires_confirmation"):
        interaction_store.update(
            req.interaction_id,
            normalized_params=v.get("normalized_params", {}),
            missing_params=[],
            requires_confirmation=True,
        )
        out = IntentResponse(
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
        logger.info(_json({
            "event": "continue_intent.end",
            "status": out.status,
            "intent": out.intent,
            "interaction_id": out.interaction_id,
        }))
        return out

    # 실행 계획
    params = v.get("normalized_params", {})
    plan = await plan_action(function_key or intent, params, shortcut=shortcut)  # ← shortcut 전달

    interaction_store.delete(req.interaction_id)

    if not plan.get("ok"):
        out = IntentResponse(
            intent=intent,
            method=req.method,
            parameters=params,
            status="error",
            message=plan.get("message", "실행 계획 생성 실패"),
            shortcut=shortcut,
            similarity=st["similarity"],
            method_used=st["method_used"],
        )
        logger.info(_json({
            "event": "continue_intent.end",
            "status": out.status,
            "intent": out.intent,
            "message": out.message,
        }))
        return out

    out = IntentResponse(
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
    logger.info(_json({
        "event": "continue_intent.end",
        "status": out.status,
        "intent": out.intent,
        "exec_kind": (out.exec or {}).get("kind") if isinstance(out.exec, dict) else None,
    }))
    return out


# -------------------- 최종 확인 --------------------
@router.post("/confirm", response_model=IntentResponse)
async def confirm_intent(req: ConfirmRequest, raw: Request):
    logger.info(_json({
        "event": "confirm_intent",
        "route": "/api/v1/userInputRe/confirm",
        "remote": _client(raw),
        "body": {
            "interaction_id": req.interaction_id,
            "confirm": bool(req.confirm),
        }
    }))

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
        out = IntentResponse(
            intent=intent,
            method=MethodName.EXECUTION,  # ← 고정 (ConfirmRequest엔 method 없음)
            parameters=params,
            status="cancelled",
            message="사용자 취소로 실행하지 않았습니다.",
            similarity=st["similarity"],
            method_used=st["method_used"],
            shortcut=shortcut,
        )
        logger.info(_json({
            "event": "confirm_intent.end",
            "status": out.status,
            "intent": out.intent,
        }))
        return out

    # 승인 → 실행 계획
    plan = await plan_action(function_key or intent, params, shortcut=shortcut)  # ← shortcut 전달
    interaction_store.delete(req.interaction_id)

    if not plan.get("ok"):
        out = IntentResponse(
            intent=intent,
            method=MethodName.EXECUTION,
            parameters=params,
            status="error",
            message=plan.get("message", "실행 계획 생성 실패"),
            shortcut=shortcut,
            similarity=st["similarity"],
            method_used=st["method_used"],
        )
        logger.info(_json({
            "event": "confirm_intent.end",
            "status": out.status,
            "intent": out.intent,
            "message": out.message,
        }))
        return out

    out = IntentResponse(
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
    logger.info(_json({
        "event": "confirm_intent.end",
        "status": out.status,
        "intent": out.intent,
        "exec_kind": (out.exec or {}).get("kind") if isinstance(out.exec, dict) else None,
    }))
    return out
