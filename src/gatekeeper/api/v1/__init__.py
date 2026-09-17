"""V1 REST API router registrations secured with API Key Authentication."""

from fastapi import APIRouter, Depends

from gatekeeper.api.security import verify_api_key
from gatekeeper.api.v1.intents import router as intents_router
from gatekeeper.api.v1.metrics import router as metrics_router

api_v1_router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(verify_api_key)],
)
api_v1_router.include_router(intents_router, prefix="/intent", tags=["Intents"])
api_v1_router.include_router(metrics_router, prefix="/metrics", tags=["Metrics"])

__all__ = ["api_v1_router"]
