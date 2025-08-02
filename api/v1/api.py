from fastapi import APIRouter
from api.v1.endpoints import intent, guide

api_router = APIRouter()
api_router.include_router(intent.router, prefix="/intent", tags=["intent"]) 
api_router.include_router(guide.router, prefix="/guide", tags=["guide"]) 