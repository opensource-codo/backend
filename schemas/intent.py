from pydantic import BaseModel
from enum import Enum
from typing import Dict, List, Optional

class UserRequest(BaseModel):
    text: str
    method: str  # GUIDE, EXECUTION 등

class IntentRequest(BaseModel):
    text: str

class MethodName(str, Enum):
    guide = "guide"
    execution = "execution"
    simulation = "simulation"

class UserRequest(BaseModel):
    text: str
    method: MethodName

class ValidateRequest(BaseModel):
    intent: str
    parameters: Dict[str, str]

class IntentResponse(BaseModel):
    intent: str
    method: MethodName
    parameters: Dict[str, str]
    status: str
    missing_params: List[str] = []
    message: str
    

class ValidationResponse(BaseModel):
    valid: bool
    missing_params: List[str]
    message: Optional[str] = None 