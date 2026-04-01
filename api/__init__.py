"""API router registry — mounts all sub-routers onto a single FastAPI APIRouter."""

from fastapi import APIRouter
from api.auth_routes import router as auth_router
from api.config_routes import router as config_router
from api.pipeline_routes import router as pipeline_router
from api.export_routes import router as export_router
from api.analytics_routes import router as analytics_router
from api.metrics_routes import router as metrics_router
from api.dashboard_routes import router as dashboard_router
from api.ab_routes import router as ab_router

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(config_router)
api_router.include_router(pipeline_router)
api_router.include_router(export_router)
api_router.include_router(analytics_router)
api_router.include_router(metrics_router)
api_router.include_router(dashboard_router)
api_router.include_router(ab_router)

__all__ = ["api_router"]
