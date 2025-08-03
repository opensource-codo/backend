from fastapi import APIRouter
from api.v1.endpoints import intent, user_input

api_router = APIRouter()
api_router.include_router(intent.router, prefix="/intent", tags=["intent"]) 
api_router.include_router(user_input.router, prefix="/userInput", tags=["userInput"])