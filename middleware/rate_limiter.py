"""In-memory rate limiting middleware for StoryForge.

Policy:
  - Default API endpoints: 60 requests per minute per IP
  - Expensive endpoints (pipeline/run, export/*): 10 requests per minute per IP

No external dependencies — uses a plain dict with (count, window_start) per IP/route-tier.
The window is a fixed 60-second tumbling window; it resets when the window expires.
"""

import time
import threading
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Thread-safe lock for the state dict
_lock = threading.Lock()

# State: (ip, tier) -> [count, window_start_time]
_state: dict[tuple[str, str], list] = {}

# Tier limits: requests per 60-second window
_LIMITS: dict[str, int] = {
    "expensive": 10,
    "default": 60,
}

# URL path prefixes that count as "expensive"
_EXPENSIVE_PREFIXES = (
    "/api/pipeline/run",
    "/api/export/",
)

_WINDOW_SECONDS = 60


def _get_ip(request: Request) -> str:
    """Extract real client IP, respecting X-Forwarded-For if trusted."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _get_tier(path: str) -> str:
    for prefix in _EXPENSIVE_PREFIXES:
        if path.startswith(prefix):
            return "expensive"
    return "default"


def _check_rate_limit(ip: str, tier: str) -> bool:
    """Return True if request is allowed, False if rate limit exceeded."""
    limit = _LIMITS[tier]
    now = time.monotonic()
    key = (ip, tier)
    with _lock:
        entry = _state.get(key)
        if entry is None or (now - entry[1]) >= _WINDOW_SECONDS:
            _state[key] = [1, now]
            return True
        if entry[0] < limit:
            entry[0] += 1
            return True
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that enforces per-IP rate limits.

    Only applies to /api/* paths. Health check (/api/health) is exempt.
    """

    EXEMPT_PATHS = {"/api/health"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Only rate-limit API routes
        if not path.startswith("/api/") or path in self.EXEMPT_PATHS:
            return await call_next(request)

        ip = _get_ip(request)
        tier = _get_tier(path)

        if not _check_rate_limit(ip, tier):
            limit = _LIMITS[tier]
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "detail": f"Rate limit exceeded: {limit} requests per minute.",
                },
                headers={"Retry-After": str(_WINDOW_SECONDS)},
            )

        return await call_next(request)
