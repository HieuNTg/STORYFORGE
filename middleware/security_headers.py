"""Security headers middleware for StoryForge.

Adds Content-Security-Policy and other security headers to all responses.
Protects the app even when accessed directly (bypassing Nginx).
"""

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request

# CSP is the single source of truth — nginx.conf intentionally omits CSP so
# this policy is never overridden or duplicated. Update only here.
#
# 'unsafe-inline' in script-src: required by Alpine.js (v3), which evaluates
# inline expressions in x-data / x-on attributes at runtime. Removing it
# breaks all Alpine.js interactivity. Tracked for removal if Alpine adds a
# CSP-compatible mode in a future release.
#
# 'unsafe-eval' in script-src: required by Alpine.js expression evaluation.
_CSP_DIRECTIVES = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-eval' 'unsafe-inline' https://cdn.jsdelivr.net",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: blob:",
    "connect-src 'self'",
    "object-src 'none'",
    "worker-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
])


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
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
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
