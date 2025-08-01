from fastapi import APIRouter
from api.v1.endpoints import intent

api_router = APIRouter()
api_router.include_router(intent.router, prefix="/intent", tags=["intent"]) 