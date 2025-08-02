from pydantic import BaseModel

class GuideRequest(BaseModel):
    text: str
    intent: str 
    shortcut: str | None = None  
