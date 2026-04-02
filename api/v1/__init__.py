"""API v1 versioned router.

Mirrors all /api/* routes under /api/v1/* so clients can pin to a stable version.
The DeprecationMiddleware adds a Deprecation response header when a v1 path is hit,
nudging clients to migrate to the unversioned /api/* endpoints.
"""

from fastapi import APIRouter, Request
from starlette.middleware.base import BaseHTTPMiddleware

from api import api_router as _base_router  # noqa: F401

# Re-export all routes under /api/v1 prefix by including the same sub-routers.
# We import individual routers rather than re-mounting api_router to avoid
# duplicate route registration on the shared FastAPI app instance.
from api.auth_routes import router as _auth
from api.config_routes import router as _config
from api.pipeline_routes import router as _pipeline
from api.export_routes import router as _export
from api.analytics_routes import router as _analytics
from api.metrics_routes import router as _metrics
from api.dashboard_routes import router as _dashboard
from api.ab_routes import router as _ab
from api.branch_routes import router as _branch
from api.audio_routes import router as _audio

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(_auth)
v1_router.include_router(_config)
v1_router.include_router(_pipeline)
v1_router.include_router(_export)
v1_router.include_router(_analytics)
v1_router.include_router(_metrics)
v1_router.include_router(_dashboard)
v1_router.include_router(_ab)
v1_router.include_router(_branch)
v1_router.include_router(_audio)

_DEPRECATION_NOTICE = (
    "The /api/v1/ prefix is provided for backward compatibility. "
    "Please migrate to /api/ (unversioned) endpoints."
)


class DeprecationMiddleware(BaseHTTPMiddleware):
    """Add a Deprecation header on all /api/v1/* responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/v1/"):
            response.headers["Deprecation"] = "true"
            response.headers["X-Deprecation-Notice"] = _DEPRECATION_NOTICE
        return response


__all__ = ["v1_router", "DeprecationMiddleware"]
