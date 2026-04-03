"""CSRF protection middleware using double-submit cookie pattern.

Sets a random CSRF token cookie on every response. State-changing requests
(POST/PUT/DELETE) must include the same token in the X-CSRF-Token header.
No server-side session storage required.
"""

import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from fastapi import Request

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_COOKIE_NAME = "csrf_token"
_HEADER_NAME = "x-csrf-token"

_EXEMPT_PREFIXES = (
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/health",
    "/api/v1/",
    "/mcp/",
)


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double-submit cookie CSRF protection."""

    async def dispatch(self, request: Request, call_next):
        if request.method not in _SAFE_METHODS:
            path = request.url.path
            if not any(path.startswith(p) for p in _EXEMPT_PREFIXES):
                cookie_token = request.cookies.get(_COOKIE_NAME, "")
                header_token = request.headers.get(_HEADER_NAME, "")
                if not cookie_token or not header_token or cookie_token != header_token:
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "CSRF token missing or invalid"},
                    )

        response = await call_next(request)

        if _COOKIE_NAME not in request.cookies:
            is_https = (
                request.url.scheme == "https"
                or request.headers.get("x-forwarded-proto") == "https"
            )
            response.set_cookie(
                key=_COOKIE_NAME,
                value=secrets.token_hex(32),
                httponly=False,
                samesite="strict",
                secure=is_https,
                path="/",
            )

        return response
