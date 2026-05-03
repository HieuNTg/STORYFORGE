"""API router registry — mounts all sub-routers onto a single FastAPI APIRouter.

Also exports ``register_exception_handlers`` to wire up the global 500 handler
on the FastAPI application instance (called from app.py).
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.auth_routes import router as auth_router
from api.config_routes import router as config_router
from api.pipeline_routes import router as pipeline_router
from api.export_routes import router as export_router
from api.analytics_routes import router as analytics_router
from api.metrics_routes import router as metrics_router
from api.dashboard_routes import router as dashboard_router
from api.ab_routes import router as ab_router
from api.branch_routes import router as branch_router
from api.feedback_routes import router as feedback_router
from api.health_routes import router as health_router
from api.usage_routes import router as usage_router
from api.eval_routes import router as eval_router
from api.share_routes import router as share_router
from api.prompt_routes import router as prompt_router
from api.continuation_routes import router as continuation_router
from api.branch_websocket import router as branch_ws_router
from api.provider_status_routes import router as provider_status_router
from api.image_routes import router as image_router
from api.quality_routes import router as quality_router

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(config_router)
api_router.include_router(pipeline_router)
api_router.include_router(continuation_router)
api_router.include_router(export_router)
api_router.include_router(analytics_router)
api_router.include_router(metrics_router)
api_router.include_router(dashboard_router)
api_router.include_router(ab_router)
api_router.include_router(branch_router)
api_router.include_router(feedback_router)
api_router.include_router(health_router)
api_router.include_router(usage_router)
api_router.include_router(eval_router)
api_router.include_router(share_router)
api_router.include_router(prompt_router)
api_router.include_router(branch_ws_router)
api_router.include_router(provider_status_router)
api_router.include_router(image_router)
api_router.include_router(quality_router)

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Error response schema
# ---------------------------------------------------------------------------

class ErrorResponse(BaseModel):
    """Consistent error payload for all 4xx/5xx API responses."""

    error: str
    request_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Exception handler registration
# ---------------------------------------------------------------------------

def register_exception_handlers(app) -> None:
    """Register global exception handlers on the FastAPI *app* instance.

    Call this from ``app.py`` after creating the FastAPI application object
    but before mounting routes.

    Handlers registered:
    - ``HTTPException`` → passthrough so intentional 4xx/5xx codes are
      preserved with a structured ``ErrorResponse`` body.
    - ``Exception`` (catch-all) → log full traceback, return generic 500
      so internal details never reach the client.
    """

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Preserve intentional HTTP errors with a structured JSON body."""
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error=exc.detail if isinstance(exc.detail, str) else str(exc.detail),
                request_id=request_id,
            ).model_dump(exclude_none=True),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Log which field/rule failed; return detail so the UI can display it."""
        request_id = getattr(request.state, "request_id", None)
        errors = exc.errors()
        # Log compact summary: loc + msg + input-length for each error
        summary = []
        for err in errors:
            loc = ".".join(str(p) for p in err.get("loc", []))
            msg = err.get("msg", "")
            input_val = err.get("input")
            input_info = f" len={len(input_val)}" if isinstance(input_val, (str, list, dict)) else ""
            summary.append(f"{loc}: {msg}{input_info}")
        _log.warning(
            "Validation failed %s [request_id=%s]: %s",
            request.url.path,
            request_id,
            " | ".join(summary),
        )
        return JSONResponse(
            status_code=422,
            content={
                "error": "Validation failed",
                "detail": errors,
                "request_id": request_id,
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        """Catch all unhandled exceptions, log with traceback, return generic 500."""
        request_id = getattr(request.state, "request_id", None)
        _log.exception(
            "Unhandled error in %s [request_id=%s]",
            request.url.path,
            request_id,
        )
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error="Internal server error",
                request_id=request_id,
            ).model_dump(exclude_none=True),
        )


__all__ = ["api_router", "register_exception_handlers", "ErrorResponse"]
