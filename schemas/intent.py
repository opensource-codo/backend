from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class IntentRequest(BaseModel):
    text: str


class MethodName(str, Enum):
    GUIDE = "GUIDE"
    EXECUTION = "EXECUTION"


class UserRequest(BaseModel):
    text: str
    method: MethodName


class ValidateRequest(BaseModel):
    intent: str
    # 파라미터가 bool/int 등일 수도 있으니 Any 권장
    parameters: Dict[str, Any]


class IntentStatus(str, Enum):
    guide_completed = "guide_completed"
    executed = "executed"
    info_required = "info_required"
    low_confidence = "low_confidence"
    confirm_required = "confirm_required"
    no_intent = "no_intent"
    unknown_method = "unknown_method",
    ready_to_execute = "ready_to_execute",
    cancelled = "cancelled",
    error = "error"


class ParamSpec(BaseModel):
    name: str
    # 예: "path" | "bool" | "enum" | "str" 등
    type: str
    description: Optional[str] = None
    choices: Optional[List[str]] = None
    default: Optional[Any] = None


class ParameterSchema(BaseModel):
    required: List[ParamSpec] = Field(default_factory=list)
    optional: List[ParamSpec] = Field(default_factory=list)
    
class IntentResponse(BaseModel):
    intent: str
    method: MethodName
    parameters: Dict[str, Any] = Field(default_factory=dict)

    status: IntentStatus
    message: Optional[str] = None

    missing_params: List[str] = Field(default_factory=list)
    parameter_schema: Optional[ParameterSchema] = None

    interaction_id: Optional[str] = None
    similarity: Optional[float] = None
    method_used: Optional[str] = None
    shortcut: Optional[str] = None

    # ✅ dict 또는 string 모두 허용 (플래너가 dict 반환해도 OK)
    exec: Optional[Union[str, Dict[str, Any]]] = None


class ValidationResponse(BaseModel):
    valid: bool
    missing_params: List[str]
    message: Optional[str] = None
