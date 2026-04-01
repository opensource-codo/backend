# services/interaction_store.py
import time
import uuid
from typing import Dict, Any, Optional

_TTL = 15 * 60  # 15분
_STORE: Dict[str, Dict[str, Any]] = {}

def _expired(rec: Dict[str, Any]) -> bool:
    return time.time() - rec.get("_ts", 0) > _TTL

def create(
    *,
    intent: str,
    function_key: str,
    normalized_params: Dict[str, Any],
    missing_params: list,
    schema: Dict[str, Any],
    shortcut: str,
    similarity: float,
    method_used: str,
    requires_confirmation: bool = False,
) -> str:
    iid = str(uuid.uuid4())
    _STORE[iid] = {
        "_ts": time.time(),
        "intent": intent,
        "function_key": function_key,
        "normalized_params": dict(normalized_params or {}),
        "missing_params": list(missing_params or []),
        "schema": schema or {"required": [], "optional": []},
        "shortcut": shortcut or "",
        "similarity": similarity,
        "method_used": method_used,
        "requires_confirmation": bool(requires_confirmation),
    }
    return iid

def get(iid: str) -> Optional[Dict[str, Any]]:
    rec = _STORE.get(iid)
    if not rec:
        return None
    if _expired(rec):
        _STORE.pop(iid, None)
        return None
    # 접근 시점 업데이트(선택)
    rec["_ts"] = time.time()
    return rec

def update(iid: str, **fields) -> Optional[Dict[str, Any]]:
    rec = get(iid)
    if not rec:
        return None
    rec.update(fields)
    rec["_ts"] = time.time()
    return rec

def delete(iid: str) -> None:
    _STORE.pop(iid, None)
