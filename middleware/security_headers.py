"""Security headers middleware for StoryForge.

Adds Content-Security-Policy and other security headers to all responses.
Applies to every response the API serves, however it is reached.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request

# CSP is the single source of truth — set only here, never by a proxy.
#
# This policy covers what the API itself serves: JSON, /media files and
# error pages. The UI is served by the Next.js server, and next/font
# self-hosts its fonts, so no third-party origin is needed.
#
# script-src keeps 'unsafe-inline' (Next.js emits inline hydration scripts)
# but no longer 'unsafe-eval' or the jsdelivr CDN, which only the retired
# Alpine.js UI needed. The API docs (STORYFORGE_DEBUG=1 only) load Swagger
# UI from a CDN, so those paths are skipped below.
_CSP_DIRECTIVES = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline'",
        "style-src 'self' 'unsafe-inline'",
        "font-src 'self'",
        "img-src 'self' data: blob:",
        "connect-src 'self'",
        "object-src 'none'",
        "worker-src 'self'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
    ]
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all HTTP responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Skip security headers for API docs (Swagger UI needs inline scripts)
        path = request.url.path
        if path in ("/docs", "/redoc", "/openapi.json"):
            return response

        response.headers["Content-Security-Policy"] = _CSP_DIRECTIVES
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"

        is_https = (
            request.url.scheme == "https"
            or request.headers.get("x-forwarded-proto") == "https"
        )
        if is_https:
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )

        return response
