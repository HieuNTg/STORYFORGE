"""Rate limiting middleware for StoryForge.

Supports two backends (auto-selected, implemented in _rate_limit_backends):
  - Redis: used when REDIS_URL env var is set (production, multi-instance safe)
  - In-memory: fallback when Redis unavailable (development, single-instance)

Policy (tuned for the single-user open-source local build):
  - Default API endpoints: 240 requests per minute per IP
  - Expensive (mutating) endpoints (pipeline/run, export/*, images/*): 60/min per IP

  These ceilings exist only as a runaway-loop / abuse backstop — a human
  clicking buttons in a single-user local build must never hit them. In dev the
  Next.js proxy collapses every request to 127.0.0.1, so the WHOLE app shares
  one per-IP bucket; tight limits there starve legitimate creative actions
  (e.g. comic generation 429'ing right after a pipeline run). Operators running
  this publicly can tighten via STORYFORGE_RATE_LIMIT_{EXPENSIVE,DEFAULT} or
  disable entirely with STORYFORGE_DISABLE_RATE_LIMIT=1.

Security:
  - X-Forwarded-For is only trusted when TRUSTED_PROXY_IPS is set (comma-separated).
    Without it, the direct client IP is used, preventing header spoofing.
"""

import logging
import os

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Stable import surface: consumers (api routes, audit middleware, tests)
# import these names from middleware.rate_limiter, not from the backends
# module. Mutable objects (_LIMITS, _lock, _state) are shared by reference.
from middleware._rate_limit_backends import (  # noqa: F401
    _LIMITS,
    _MAX_MEMORY_ENTRIES,
    _REDIS_RATE_LIMIT_SCRIPT,
    _WINDOW_SECONDS,
    _check_rate_limit_memory,
    _check_rate_limit_redis,
    _evict_expired_entries,
    _get_redis,
    _lock,
    _state,
)

logger = logging.getLogger(__name__)

_EXPENSIVE_PREFIXES = (
    "/api/pipeline/run",
    "/api/export/",
    "/api/images/",
)

# Trusted proxy IPs — only trust X-Forwarded-For from these addresses.
# Set TRUSTED_PROXY_IPS=127.0.0.1,10.0.0.1 in production (Nginx, load balancer).
_TRUSTED_PROXIES: set[str] = set()
_raw_proxies = os.environ.get("TRUSTED_PROXY_IPS", "")
if _raw_proxies.strip():
    _TRUSTED_PROXIES = {ip.strip() for ip in _raw_proxies.split(",") if ip.strip()}
else:
    logger.warning(
        "TRUSTED_PROXY_IPS not configured. X-Forwarded-For headers will be ignored. "
        "Set TRUSTED_PROXY_IPS for proper client IP detection behind a proxy."
    )


def _get_ip(request: Request) -> str:
    """Extract client IP. Only trusts X-Forwarded-For from trusted proxies."""
    client_ip = request.client.host if request.client else "unknown"

    if _TRUSTED_PROXIES and client_ip in _TRUSTED_PROXIES:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

    return client_ip


def _get_tier(path: str, method: str = "POST") -> str:
    # Only mutating requests that kick off heavy work count as expensive. Heavy
    # work (pipeline run, export build, image/comic generation) is always POST;
    # GETs are status reads — most importantly the async comic-job poll
    # (GET /api/images/library/jobs/{id}), which fires every ~2.5s and would
    # otherwise blow the expensive budget in seconds, surfacing as a spurious
    # "Too Many Requests" toast mid-generation. DELETE (job cancel) is a cheap
    # control op, not heavy work, so it is exempt too.
    if method.upper() in ("GET", "HEAD", "OPTIONS", "DELETE"):
        return "default"
    for prefix in _EXPENSIVE_PREFIXES:
        if path.startswith(prefix):
            return "expensive"
    return "default"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that enforces per-IP rate limits.

    Auto-selects Redis backend when REDIS_URL is set, otherwise in-memory.
    Only applies to /api/* paths. Health check (/api/health) is exempt.
    """

    EXEMPT_PATHS = {"/api/health", "/api/metrics"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Only rate-limit API routes. Test/dev browser suites can opt out or raise
        # limits via env without changing production defaults.
        if (
            os.environ.get("STORYFORGE_DISABLE_RATE_LIMIT", "").lower()
            in ("1", "true", "yes")
            or not path.startswith("/api/")
            or path in self.EXEMPT_PATHS
        ):
            return await call_next(request)

        ip = _get_ip(request)
        tier = _get_tier(path, request.method)

        # Use Redis if available, otherwise in-memory
        allowed = (
            _check_rate_limit_redis(ip, tier)
            if os.environ.get("REDIS_URL")
            else _check_rate_limit_memory(ip, tier)
        )

        if not allowed:
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
