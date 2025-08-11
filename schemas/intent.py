from pydantic import BaseModel, Field
from enum import Enum
from typing import Any, Dict, List, Optional, Literal

class UserRequest(BaseModel):
    text: str
    method: str  # GUIDE, EXECUTION 등

class IntentRequest(BaseModel):
    text: str

class MethodName(str, Enum):
    guide = "GUIDE"
    execution = "EXECUTION"
    # simulation = "simulation"

class UserRequest(BaseModel):
    text: str
    method: MethodName

class ValidateRequest(BaseModel):
    intent: str
    parameters: Dict[str, str]

class IntentStatus(str, Enum):
    guide_completed = "guide_completed"
    executed = "executed"
    info_required = "info_required"
    low_confidence = "low_confidence"
    confirm_required = "confirm_required"
    no_intent = "no_intent"
    unknown_method = "unknown_method"

    
class ParamSpec(BaseModel):
    name: str
    type: str  # 예: "path" | "bool" | "enum" | "str" 등
    description: Optional[str] = None
    choices: Optional[List[str]] = None
    default: Optional[Any] = None


class ParameterSchema(BaseModel):
    required: List[ParamSpec] = Field(default_factory=list)
    optional: List[ParamSpec] = Field(default_factory=list)


class IntentResponse(BaseModel):
    intent: str
    method: "MethodName"  # 또는 위 주석의 Enum 사용
    parameters: Dict[str, Any] = Field(default_factory=dict)

    status: IntentStatus
    message: str

    missing_params: List[str] = Field(default_factory=list)
    parameter_schema: Optional[ParameterSchema] = None

    interaction_id: Optional[str] = None
    similarity: Optional[float] = None
    method_used: Optional[Literal["rag", "llm"]] = None
    shortcut: Optional[str] = None
    

class ValidationResponse(BaseModel):
    valid: bool
    missing_params: List[str]
    message: Optional[str] = None 