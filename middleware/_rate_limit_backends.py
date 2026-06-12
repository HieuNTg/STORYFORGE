"""Rate-limit check backends for middleware/rate_limiter.py.

Two interchangeable per-IP fixed-window backends:
  - In-memory: development fallback, single-instance only
  - Redis: production, multi-instance safe (atomic Lua INCR+EXPIRE)

Internal module — import these names via middleware.rate_limiter, which
re-exports them as the stable patch/import surface.
"""

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

_LIMITS: dict[str, int] = {
    "expensive": int(os.environ.get("STORYFORGE_RATE_LIMIT_EXPENSIVE", "60")),
    "default": int(os.environ.get("STORYFORGE_RATE_LIMIT_DEFAULT", "240")),
}

_WINDOW_SECONDS = 60

# Max entries in in-memory state before eviction sweep
_MAX_MEMORY_ENTRIES = 10_000


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
        logger.warning(
            "Rate limiter: Redis unavailable (%s), falling back to in-memory", exc
        )
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
