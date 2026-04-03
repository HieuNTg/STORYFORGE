"""Request trace ID middleware — attaches a UUID4 trace ID to every request.

Uses contextvars so the ID is accessible anywhere in the request's call stack
without passing it explicitly. Reads X-Request-ID from incoming headers if
present, otherwise generates a new UUID4.
"""

import uuid
from contextvars import ContextVar

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


def get_trace_id() -> str:
    """Return the trace ID for the current request context."""
    return _trace_id_var.get()


class TraceIDMiddleware(BaseHTTPMiddleware):
    """Set a per-request trace ID and expose it via X-Request-ID response header."""

    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = _trace_id_var.set(trace_id)
        try:
            response = await call_next(request)
        finally:
            _trace_id_var.reset(token)
        response.headers["X-Request-ID"] = trace_id
        return response
