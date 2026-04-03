"""Audit logging middleware — logs each API request with IP, method, path, and status.

Writes structured log entries so security audits can trace all API access.
Skips static file serving to keep logs focused on API traffic.

IP extraction uses the same trusted-proxy validation as the rate limiter:
X-Forwarded-For is only trusted when the direct client is a known proxy IP
(configured via TRUSTED_PROXY_IPS env var). This prevents audit log spoofing.
"""

import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

# Import trusted proxy set from rate_limiter — single source of truth for
# which upstream addresses are allowed to set X-Forwarded-For.
from middleware.rate_limiter import _TRUSTED_PROXIES

logger = logging.getLogger("audit")

_SKIP_PREFIXES = ("/static/", "/gradio/", "/favicon")


class AuditMiddleware(BaseHTTPMiddleware):
    """Log every API request: timestamp, IP, method, path, status, duration."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip static assets and Gradio traffic — no security value in auditing these
        for prefix in _SKIP_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        start = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 1)

        ip = _get_ip(request)
        logger.info(
            "audit",
            extra={
                "event": "http_request",
                "ip": ip,
                "method": request.method,
                "path": path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
        )

        return response


def _get_ip(request: Request) -> str:
    """Extract client IP with trusted-proxy validation.

    Only trusts X-Forwarded-For when the direct client IP is in TRUSTED_PROXIES,
    matching the rate limiter's validation logic to prevent log spoofing.
    """
    client_ip = request.client.host if request.client else "unknown"

    if _TRUSTED_PROXIES and client_ip in _TRUSTED_PROXIES:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

    return client_ip
