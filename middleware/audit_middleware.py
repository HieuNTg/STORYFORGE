"""FastAPI middleware that auto-logs security-relevant HTTP requests.

Captures:
  - All POST / PUT / PATCH / DELETE requests (state-changing)
  - All requests to auth, config, pipeline/run, and export paths
  - Response status code and derived result (success / failure / error)

Skips:
  - GET requests to non-sensitive paths
  - /api/health and /api/metrics
  - Non-API paths (static assets, Gradio, etc.)

JWT user extraction: decodes the payload segment WITHOUT signature verification
(the upstream auth middleware already guards protected routes). This lets us
record the user_id even on failed auth attempts.
"""
import base64
import json
import logging
from typing import Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from services.audit_logger import get_audit_logger

logger = logging.getLogger(__name__)

# Paths that are never audited
_SKIP_PATHS = frozenset({"/api/health", "/api/metrics"})

# HTTP methods that always trigger an audit record
_AUDIT_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})

# Prefixes where even GET requests are audited (e.g., token refresh, download)
_ALWAYS_AUDIT_PREFIXES = (
    "/api/auth/",
    "/api/config/",
    "/api/pipeline/run",
    "/api/export/",
)

# Mapping from path prefix -> action label (checked in order)
_ACTION_MAP = [
    ("/api/auth/login",    "auth_login"),
    ("/api/auth/register", "auth_register"),
    ("/api/auth/logout",   "auth_logout"),
    ("/api/auth/",         "auth_event"),
    ("/api/config/",       "config_change"),
    ("/api/pipeline/run",  "pipeline_run"),
    ("/api/export/",       "export"),
]
_METHOD_ACTIONS = {"POST": "create", "PUT": "update", "PATCH": "update", "DELETE": "delete"}


def _should_audit(method: str, path: str) -> bool:
    """Return True if this request warrants an audit record."""
    if not path.startswith("/api/"):
        return False
    if path in _SKIP_PATHS:
        return False
    if method in _AUDIT_METHODS:
        return True
    for prefix in _ALWAYS_AUDIT_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


def _extract_ip(request: Request) -> str:
    """Extract real client IP, honouring X-Forwarded-For for reverse proxies."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _extract_user_id(request: Request) -> Optional[str]:
    """Extract 'sub' claim from JWT payload without verifying the signature.

    Safe for audit use: we only want the identifier, not authorization.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        parts = auth[7:].split(".")
        if len(parts) != 3:
            return None
        b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(b64)).get("sub")
    except Exception:
        return None


def _action_label(method: str, path: str) -> str:
    """Derive a short action label from the HTTP method and path."""
    for prefix, label in _ACTION_MAP:
        if path.startswith(prefix):
            return label
    return _METHOD_ACTIONS.get(method, method.lower())


class AuditMiddleware(BaseHTTPMiddleware):
    """Starlette/FastAPI middleware that records security-relevant requests.

    Should be added AFTER RateLimitMiddleware so rate-limited requests
    (rejected before routing) are not unnecessarily logged.
    """

    async def dispatch(self, request: Request, call_next):
        """Pass request downstream, then write an audit record if warranted.

        Args:
            request: Incoming HTTP request.
            call_next: Next middleware / route handler.

        Returns:
            HTTP response from the downstream handler.
        """
        method = request.method.upper()
        path = request.url.path

        if not _should_audit(method, path):
            return await call_next(request)

        ip = _extract_ip(request)
        user_id = _extract_user_id(request)
        user_agent = request.headers.get("User-Agent", "")
        action = _action_label(method, path)

        result = "success"
        status_code = 200
        try:
            response = await call_next(request)
            status_code = response.status_code
            if status_code >= 500:
                result = "error"
            elif status_code >= 400:
                result = "failure"
        except Exception:
            result = "error"
            raise
        finally:
            get_audit_logger().log_event(
                action=action,
                resource=path,
                user_id=user_id,
                ip=ip,
                result=result,
                details={"method": method, "status_code": status_code},
                user_agent=user_agent,
            )

        return response
