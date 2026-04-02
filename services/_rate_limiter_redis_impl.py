"""RedisRateLimiter — sliding-window rate limiter backed by Redis sorted sets.

Internal module; public API is via services.rate_limiter_redis.

Algorithm (atomic Lua script):
  1. ZREMRANGEBYSCORE — evict timestamps older than the window
  2. ZADD             — record the current request timestamp (ms)
  3. ZCARD            — count active entries
  4. EXPIRE           — schedule key cleanup

Falls back to InMemoryRateLimiter on any Redis error.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from services._rate_limiter_base import RateLimiterBase

logger = logging.getLogger(__name__)

_LUA_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local cutoff = now - window_ms
redis.call('ZREMRANGEBYSCORE', key, 0, cutoff)
redis.call('ZADD', key, now, now)
local count = redis.call('ZCARD', key)
redis.call('EXPIRE', key, math.ceil(window_ms / 1000) + 1)
return count
"""


class RedisRateLimiter(RateLimiterBase):
    """Sliding-window rate limiter using Redis sorted sets.

    Automatically falls back to in-memory if Redis is unavailable.
    """

    def __init__(self, redis_url: str) -> None:
        from services._rate_limiter_inmemory import InMemoryRateLimiter
        self._redis_url = redis_url
        self._client: Optional[object] = None
        self._script_sha: Optional[str] = None
        self._fallback = InMemoryRateLimiter()
        self._healthy = False
        self._connect()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _connect(self) -> None:
        try:
            import redis  # type: ignore[import]
            client = redis.from_url(
                self._redis_url,
                socket_connect_timeout=2,
                socket_timeout=2,
                decode_responses=False,
            )
            client.ping()
            self._client = client
            self._script_sha = client.script_load(_LUA_SCRIPT)
            self._healthy = True
            logger.info("RedisRateLimiter: connected (%s…)", self._redis_url[:30])
        except Exception as exc:
            logger.warning(
                "RedisRateLimiter: unavailable (%s) — falling back to in-memory", exc
            )
            self._healthy = False

    def _eval(self, key: str, limit: int, window_seconds: int) -> Optional[int]:
        """Run Lua script atomically; return request count or None on error."""
        if not self._healthy or self._client is None:
            return None
        try:
            now_ms = int(time.time() * 1000)
            count = self._client.evalsha(  # type: ignore[attr-defined]
                self._script_sha, 1, key,
                now_ms, window_seconds * 1000, limit
            )
            return int(count)
        except Exception as exc:
            logger.warning("RedisRateLimiter: error, degrading to in-memory — %s", exc)
            self._healthy = False
            return None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def is_allowed(self, key: str, limit: int, window_seconds: int) -> bool:
        count = self._eval(key, limit, window_seconds)
        if count is None:
            return self._fallback.is_allowed(key, limit, window_seconds)
        return count <= limit

    def get_remaining(self, key: str, limit: int, window_seconds: int) -> int:
        if not self._healthy or self._client is None:
            return self._fallback.get_remaining(key, limit, window_seconds)
        try:
            now_ms = int(time.time() * 1000)
            cutoff_ms = now_ms - (window_seconds * 1000)
            count = self._client.zcount(key, cutoff_ms, "+inf")  # type: ignore[attr-defined]
            return max(0, limit - int(count))
        except Exception as exc:
            logger.warning("RedisRateLimiter: get_remaining fallback — %s", exc)
            return self._fallback.get_remaining(key, limit, window_seconds)
