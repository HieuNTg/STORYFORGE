"""Middleware that auto-records HTTP request metrics via the prometheus_metrics singleton.

Skips /api/health to avoid noise in dashboards.
"""

import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from services.prometheus_metrics import prometheus_metrics

_SKIP_PATHS = {"/api/health"}


class MetricsMiddleware(BaseHTTPMiddleware):
    """Times each request and records method, path, status, and duration."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if path in _SKIP_PATHS:
            return await call_next(request)

        start = time.monotonic()
        response = await call_next(request)
        duration_ms = (time.monotonic() - start) * 1000.0

        prometheus_metrics.record_request(
            method=request.method,
            path=path,
            status=response.status_code,
            duration_ms=duration_ms,
        )

        return response
