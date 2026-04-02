"""API v1 package.

Exposes:
  - v1_router:              the assembled /api/v1 APIRouter (lazy-built on first access)
  - DeprecationMiddleware:  Starlette middleware that adds a Deprecation header to all
                            requests whose path starts with /api/ but NOT /api/v1/.
                            Mount this on the FastAPI app alongside v1_router to guide
                            clients toward the versioned endpoints.

Usage in app.py (when ready to enable versioned routing):

    from api.v1 import v1_router, DeprecationMiddleware
    main_app.add_middleware(DeprecationMiddleware)
    main_app.include_router(v1_router)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from api.v1.router import build_v1_router

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy singleton router
# ---------------------------------------------------------------------------

_v1_router: APIRouter | None = None


def _get_v1_router() -> APIRouter:
    global _v1_router
    if _v1_router is None:
        _v1_router = build_v1_router()
    return _v1_router


# Public name — callers do: from api.v1 import v1_router
v1_router: APIRouter = _get_v1_router()  # type: ignore[assignment]
# Using property-like lazy initialisation; reassign so the name is importable directly.
v1_router = _get_v1_router()


# ---------------------------------------------------------------------------
# Deprecation middleware
# ---------------------------------------------------------------------------

_DEPRECATION_LINK = "https://docs.storyforge.io/api/migration-v1"


class DeprecationMiddleware(BaseHTTPMiddleware):
    """Add Deprecation + Sunset headers for non-versioned /api/* requests.

    Any request to /api/<path> that does NOT start with /api/v1/ is treated
    as a legacy (non-versioned) call and receives:
      - Deprecation: true
      - Link: <docs-url>; rel="deprecation"
      - Sunset: (informational date set in STORYFORGE_API_SUNSET env var)

    This allows clients to detect the deprecation via standard HTTP headers
    without breaking existing integrations.
    """

    EXEMPT_PREFIXES = ("/api/v1/", "/api/health")

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        is_legacy_api = (
            path.startswith("/api/")
            and not any(path.startswith(p) for p in self.EXEMPT_PREFIXES)
        )

        response: Response = await call_next(request)

        if is_legacy_api:
            response.headers["Deprecation"] = "true"
            response.headers["Link"] = f'<{_DEPRECATION_LINK}>; rel="deprecation"'
            logger.debug(
                "deprecation_middleware: legacy path %s — deprecation header added", path
            )

        return response


__all__ = ["v1_router", "DeprecationMiddleware"]
