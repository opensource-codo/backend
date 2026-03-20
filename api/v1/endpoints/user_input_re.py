from __future__ import annotations

import os, json, logging
from fastapi import APIRouter, Request

from schemas.intent import UserRequest, IntentResponse
from schemas.requests import ContinueRequest, ConfirmRequest
from use_cases.handle_intent import handle_intent
from use_cases.continue_intent import continue_intent
from use_cases.confirm_intent import confirm_intent

router = APIRouter()
os.makedirs("logs", exist_ok=True)
logger = logging.getLogger("codo.user_input")
if not logger.handlers:
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.FileHandler("logs/user_input.log", encoding="utf-8")
    fh.setFormatter(fmt)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)
    logger.setLevel(logging.INFO)


def _mth(v) -> str:
    if hasattr(v, "value"):
        return str(v.value).upper()
    return str(v).upper()


def _json(o) -> str:
    try:
        return json.dumps(o, ensure_ascii=False)
    except Exception:
        return str(o)


def _client(req: Request) -> str:
    return getattr(req.client, "host", "?") if req and req.client else "?"


@router.post("/", response_model=IntentResponse)
async def handle_user_input(payload: UserRequest, req: Request):
    logger.info(_json({
        "event": "handle_user_input",
        "route": "/api/v1/userInputRe/",
        "remote": _client(req),
        "body": {"text": payload.text, "method": _mth(payload.method)},
    }))
    return await handle_intent(payload.text, payload.method)


@router.post("/continue", response_model=IntentResponse)
async def continue_intent_endpoint(req: ContinueRequest, raw: Request):
    logger.info(_json({
        "event": "continue_intent",
        "route": "/api/v1/userInputRe/continue",
        "remote": _client(raw),
        "body": {"interaction_id": req.interaction_id, "method": _mth(req.method), "parameters": req.parameters or {}},
    }))
    return await continue_intent(req.interaction_id, req.parameters, req.text, req.method)


@router.post("/confirm", response_model=IntentResponse)
async def confirm_intent_endpoint(req: ConfirmRequest, raw: Request):
    logger.info(_json({
        "event": "confirm_intent",
        "route": "/api/v1/userInputRe/confirm",
        "remote": _client(raw),
        "body": {"interaction_id": req.interaction_id, "confirm": bool(req.confirm)},
    }))
    return await confirm_intent(req.interaction_id, req.confirm)
