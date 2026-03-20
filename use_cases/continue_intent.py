from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import HTTPException

from services.validator_service import validate, validator_service
from services.executor_service import plan_action
from services import interaction_store

from schemas.intent import MethodName, IntentResponse

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


async def continue_intent(
    interaction_id: str,
    parameters: dict,
    text: Optional[str],
    method: MethodName,
) -> IntentResponse:
    st = interaction_store.get(interaction_id)
    if not st:
        raise HTTPException(status_code=404, detail="유효하지 않은 interaction_id 입니다. 시간이 만료되었을 수 있어요.")

    intent = st["intent"]
    function_key = st["function_key"]
    shortcut = st["shortcut"]

    # 누적 파라미터 병합
    merged = dict(st.get("normalized_params", {}))
    merged.update(parameters or {})

    # 재검증 (RAG 없음!)
    v = validate(intent, parameters=merged, text=text or "", method=_mth(method))
    schema = st.get("schema") or validator_service.get_intent_params(intent)

    if not v["valid"]:
        interaction_store.update(
            interaction_id,
            normalized_params=v.get("normalized_params", {}),
            missing_params=v.get("missing_params", []),
            schema=schema,
            requires_confirmation=False,
        )
        out = IntentResponse(
            intent=intent,
            method=method,
            parameters=v.get("normalized_params", {}),
            status="info_required",
            missing_params=v.get("missing_params", []),
            parameter_schema=schema,
            message=v.get("message", "아직 필요한 정보가 더 있어요."),
            interaction_id=interaction_id,
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
            interaction_id,
            normalized_params=v.get("normalized_params", {}),
            missing_params=[],
            requires_confirmation=True,
        )
        out = IntentResponse(
            intent=intent,
            method=method,
            parameters=v.get("normalized_params", {}),
            status="confirm_required",
            message="이 작업은 위험할 수 있어요. 확인 후 다시 실행해주세요.",
            interaction_id=interaction_id,
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
    plan = await plan_action(function_key or intent, params, shortcut=shortcut)

    interaction_store.delete(interaction_id)

    if not plan.get("ok"):
        out = IntentResponse(
            intent=intent,
            method=method,
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
        method=method,
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
