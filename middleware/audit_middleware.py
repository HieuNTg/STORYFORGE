"""Audit logging middleware — logs each API request with IP, method, path, and status.

Writes structured log entries so security audits can trace all API access.
Skips static file serving to keep logs focused on API traffic.
"""

import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

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
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
