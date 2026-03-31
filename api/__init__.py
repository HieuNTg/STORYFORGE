"""API router registry — mounts all sub-routers onto a single FastAPI APIRouter."""

from fastapi import APIRouter
from api.config_routes import router as config_router
from api.pipeline_routes import router as pipeline_router
from api.export_routes import router as export_router

api_router = APIRouter(prefix="/api")
api_router.include_router(config_router)
api_router.include_router(pipeline_router)
api_router.include_router(export_router)

__all__ = ["api_router"]
