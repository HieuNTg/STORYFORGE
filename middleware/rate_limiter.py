"""Rate limiting middleware for StoryForge.

Supports two backends (auto-selected):
  - Redis: used when REDIS_URL env var is set (production, multi-instance safe)
  - In-memory: fallback when Redis unavailable (development, single-instance)

Policy:
  - Default API endpoints: 60 requests per minute per IP
  - Expensive endpoints (pipeline/run, export/*): 10 requests per minute per IP

Security:
  - X-Forwarded-For is only trusted when TRUSTED_PROXY_IPS is set (comma-separated).
    Without it, the direct client IP is used, preventing header spoofing.
"""

import logging
import os
import time
import threading
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tier configuration
# ---------------------------------------------------------------------------
_LIMITS: dict[str, int] = {
    "expensive": 10,
    "default": 60,
}

_EXPENSIVE_PREFIXES = (
    "/api/pipeline/run",
    "/api/export/",
    "/api/images/",
)

_WINDOW_SECONDS = 60

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

# Max entries in in-memory state before eviction sweep
_MAX_MEMORY_ENTRIES = 10_000


def _get_ip(request: Request) -> str:
    """Extract client IP. Only trusts X-Forwarded-For from trusted proxies."""
    client_ip = request.client.host if request.client else "unknown"

    if _TRUSTED_PROXIES and client_ip in _TRUSTED_PROXIES:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

    return client_ip


def _get_tier(path: str) -> str:
    for prefix in _EXPENSIVE_PREFIXES:
        if path.startswith(prefix):
            return "expensive"
    return "default"


# ---------------------------------------------------------------------------
# In-memory backend (development fallback)
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_state: dict[tuple[str, str], list] = {}


def _evict_expired_entries() -> None:
    """Remove expired entries from in-memory state (called under _lock)."""
    now = time.monotonic()
    expired = [k for k, v in _state.items() if (now - v[1]) >= _WINDOW_SECONDS]
    for k in expired:
        del _state[k]


def _check_rate_limit_memory(ip: str, tier: str) -> bool:
    """In-memory rate check. Returns True if request is allowed."""
    limit = _LIMITS[tier]
    now = time.monotonic()
    key = (ip, tier)
    with _lock:
        # Periodic eviction to prevent unbounded memory growth
        if len(_state) > _MAX_MEMORY_ENTRIES:
            _evict_expired_entries()

        entry = _state.get(key)
        if entry is None or (now - entry[1]) >= _WINDOW_SECONDS:
            _state[key] = [1, now]
            return True
        if entry[0] < limit:
            entry[0] += 1
            return True
        return False


# ---------------------------------------------------------------------------
# Redis backend (production, multi-instance safe)
# ---------------------------------------------------------------------------
_redis_client = None
_redis_init_attempted = False


def _get_redis():
    """Lazily initialize Redis connection. Returns None if unavailable."""
    global _redis_client, _redis_init_attempted
    if _redis_init_attempted:
        return _redis_client

    _redis_init_attempted = True
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        return None

    try:
        import redis
        _redis_client = redis.from_url(redis_url, decode_responses=True)
        _redis_client.ping()
        logger.info("Rate limiter: using Redis backend at %s", redis_url)
        return _redis_client
    except Exception as exc:
        logger.warning("Rate limiter: Redis unavailable (%s), falling back to in-memory", exc)
        _redis_client = None
        return None


# Lua script for atomic INCR + EXPIRE in a single round-trip.
# Returns the current count after increment.
_REDIS_RATE_LIMIT_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""


def _check_rate_limit_redis(ip: str, tier: str) -> bool:
    """Redis-backed rate check using atomic Lua script."""
    r = _get_redis()
    if r is None:
        return _check_rate_limit_memory(ip, tier)

    limit = _LIMITS[tier]
    key = f"sf:ratelimit:{ip}:{tier}"

    try:
        current_count = r.eval(_REDIS_RATE_LIMIT_SCRIPT, 1, key, _WINDOW_SECONDS)
        return current_count <= limit
    except Exception as exc:
        logger.warning("Rate limiter: Redis error (%s), falling back to in-memory", exc)
        return _check_rate_limit_memory(ip, tier)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
class RateLimitMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that enforces per-IP rate limits.

    Auto-selects Redis backend when REDIS_URL is set, otherwise in-memory.
    Only applies to /api/* paths. Health check (/api/health) is exempt.
    """

    EXEMPT_PATHS = {"/api/health", "/api/metrics"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Only rate-limit API routes
        if not path.startswith("/api/") or path in self.EXEMPT_PATHS:
            return await call_next(request)

        ip = _get_ip(request)
        tier = _get_tier(path)

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
