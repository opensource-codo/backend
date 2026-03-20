from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

from schemas.intent import MethodName


class ContinueRequest(BaseModel):
    interaction_id: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    text: Optional[str] = None
    method: MethodName = MethodName.EXECUTION  # 보강도 EXECUTION 기준 검증


class ConfirmRequest(BaseModel):
    interaction_id: str
    confirm: bool = True
