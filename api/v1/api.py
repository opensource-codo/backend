from fastapi import APIRouter
from api.v1.endpoints import user_input, front_test

api_router = APIRouter() 
api_router.include_router(user_input.router, prefix="/userInput", tags=["userInput"])
api_router.include_router(front_test.router, prefix="/front-test", tags=["userInput"])