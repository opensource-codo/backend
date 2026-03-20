from __future__ import annotations

import json
import logging

from fastapi import HTTPException

from services.executor_service import plan_action
from services import interaction_store

from schemas.intent import MethodName, IntentResponse

logger = logging.getLogger("codo.user_input")


def _json(o) -> str:
    try:
        return json.dumps(o, ensure_ascii=False)
    except Exception:
        return str(o)


async def confirm_intent(interaction_id: str, confirm: bool) -> IntentResponse:
    st = interaction_store.get(interaction_id)
    if not st:
        raise HTTPException(status_code=404, detail="유효하지 않은 interaction_id 입니다. 시간이 만료되었을 수 있어요.")

    intent = st["intent"]
    function_key = st["function_key"]
    shortcut = st["shortcut"]
    params = st.get("normalized_params", {})

    if not st.get("requires_confirmation"):
        raise HTTPException(status_code=400, detail="현재 흐름은 확인이 필요한 상태가 아닙니다.")

    if not confirm:
        interaction_store.delete(interaction_id)
        out = IntentResponse(
            intent=intent,
            method=MethodName.EXECUTION,
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
    plan = await plan_action(function_key or intent, params, shortcut=shortcut)
    interaction_store.delete(interaction_id)

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
