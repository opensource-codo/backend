from __future__ import annotations

import json
import logging
from typing import Optional

from services.ui_guide_service import build_ui_guide
from services.intent_service import extract_intent_with_rag, db_get_function_info, search_similar_intents
from services.validator_service import validate, validator_service
from services.executor_service import plan_action
from services import interaction_store
from services.param_extractor import extract_params_llm

from schemas.intent import UserRequest, MethodName, IntentResponse
from core.config import settings

logger = logging.getLogger("codo.user_input")


def _mth(v) -> str:
    if hasattr(v, "value"):
        return str(v.value).upper()
    return str(v).upper()


def _json(o) -> str:
    try:
        return json.dumps(o, ensure_ascii=False)
    except Exception:
        return str(o)


async def handle_intent(text: str, method: MethodName) -> IntentResponse:
    # 1) RAG로 intent 추출
    intent_result = await extract_intent_with_rag(text)
    intent = (intent_result.get("intent") or "").strip()
    similarity = float(intent_result.get("similarity", 0.0))
    method_used = intent_result.get("method", "unknown")
    function_key_from_rag = (intent_result.get("function_key") or "").strip()

    # (A) intent가 비었으면: 별칭/폴백으로 function_key 추정
    alias_fk: Optional[str] = None
    if not intent:
        try:
            alias_fk = validator_service._get_function_key_from_intent(text or "")
        except Exception:
            alias_fk = None
        if alias_fk:
            intent = (text or alias_fk).strip()
            function_key_from_rag = function_key_from_rag or alias_fk
            method_used = f"{method_used}+alias_fallback" if method_used else "alias_fallback"
            similarity = max(similarity, 0.99)

    # (B) intent가 끝내 비면 no_intent
    if not intent:
        alts = await search_similar_intents(text, n_results=5)
        out = IntentResponse(
            intent="",
            method=method,
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
        fn = db_get_function_info(intent) or db_get_function_info(function_key_from_rag) or {}
        shortcut = fn.get("shortcut", "")
    else:
        fn = db_get_function_info(intent) or {}
        function_key = (fn.get("function_key") or "").strip()
        shortcut = fn.get("shortcut") or ""
        if not function_key:
            try:
                function_key = validator_service._get_function_key_from_intent(intent) or ""
            except Exception:
                function_key = ""

    # 3) GUIDE
    if method == MethodName.GUIDE:
        guide_result = build_ui_guide(function_key or intent, fn or {})
        guide = guide_result.get("message_markdown", "")
        out = IntentResponse(
            intent=intent,
            method=method,
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

    if schema.get("not_configured"):
        out = IntentResponse(
            intent=intent,
            method=method,
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

    if similarity < settings.SIM_THRESHOLD and not function_key_from_rag and not function_key:
        alts = await search_similar_intents(text, n_results=5)
        out = IntentResponse(
            intent=intent,
            method=method,
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

    if method == MethodName.EXECUTION:
        pre_params = extract_params_llm(intent, text, schema) or {}
        v = validate(intent, pre_params, text=text, method=_mth(method))
    else:
        out = IntentResponse(
            intent=intent,
            method=method,
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
            method=method,
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
            method=method,
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

    # 5) 실행 계획 생성
    params = v.get("normalized_params", {})
    plan = await plan_action(function_key or intent, params, shortcut=shortcut)

    if not plan.get("ok"):
        out = IntentResponse(
            intent=intent,
            method=method,
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
        method=method,
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
