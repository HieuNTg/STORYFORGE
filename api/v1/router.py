"""Central v1 router — aggregates all versioned route groups.

Every response from this router carries the X-API-Version: v1 header,
injected via a lightweight route_class override.

Route groups:
  /api/v1/pipeline   — story generation pipeline
  /api/v1/config     — settings management
  /api/v1/export     — export to PDF / EPUB / etc.
  /api/v1/audio      — text-to-speech
  /api/v1/analytics  — usage analytics
  /api/v1/auth       — authentication
  /api/v1/branch     — story branching
  /api/v1/dashboard  — dashboard summary
  /api/v1/feedback   — user feedback (placeholder)
"""

from __future__ import annotations

import logging
from typing import Callable

from fastapi import APIRouter, Request, Response
from fastapi.routing import APIRoute

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Version header injection via custom APIRoute
# ---------------------------------------------------------------------------

_API_VERSION = "v1"


class _VersionedRoute(APIRoute):
    """APIRoute subclass that appends X-API-Version to every response."""

    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def route_handler(request: Request) -> Response:
            response: Response = await original(request)
            response.headers["X-API-Version"] = _API_VERSION
            return response

        return route_handler


# ---------------------------------------------------------------------------
# Placeholder routers (feedback — Sprint N+1)
# ---------------------------------------------------------------------------

_feedback_router = APIRouter(prefix="/feedback", tags=["feedback"])


@_feedback_router.post("")
async def submit_feedback():
    """Placeholder — user feedback submission (not yet implemented)."""
    return {"message": "Feedback endpoint coming soon.", "version": _API_VERSION}


@_feedback_router.get("")
async def list_feedback():
    """Placeholder — list feedback entries (not yet implemented)."""
    return {"message": "Feedback listing coming soon.", "version": _API_VERSION}



# ---------------------------------------------------------------------------
# v1 router assembly
# ---------------------------------------------------------------------------

def build_v1_router() -> APIRouter:
    """Construct and return the /api/v1 router with all sub-groups included.

    Importing route modules is deferred to this factory to avoid circular
    imports at module load time and to keep startup cost explicit.
    """
    from api.pipeline_routes import router as pipeline_router
    from api.config_routes import router as config_router
    from api.export_routes import router as export_router
    from api.audio_routes import router as audio_router
    from api.analytics_routes import router as analytics_router
    from api.auth_routes import router as auth_router
    from api.branch_routes import router as branch_router
    from api.dashboard_routes import router as dashboard_router

    v1 = APIRouter(prefix="/api/v1", route_class=_VersionedRoute)

    v1.include_router(pipeline_router)
    v1.include_router(config_router)
    v1.include_router(export_router)
    v1.include_router(audio_router)
    v1.include_router(analytics_router)
    v1.include_router(auth_router)
    v1.include_router(branch_router)
    v1.include_router(dashboard_router)
    v1.include_router(_feedback_router)

    logger.info("api/v1: router built with %d routes", len(v1.routes))
    return v1
