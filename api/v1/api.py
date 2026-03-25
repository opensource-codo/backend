from fastapi import APIRouter
from api.v1.endpoints import user_input_re
from api.v1.guide import router as guide_router

api_router = APIRouter()
# api_router.include_router(user_input.router, prefix="/userInput", tags=["userInput"])
api_router.include_router(guide_router, prefix="", tags=["guide"])
api_router.include_router(user_input_re.router, prefix="/userInputRe", tags=["userInputRe"])