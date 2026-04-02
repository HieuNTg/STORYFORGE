"""Redis-backed and in-memory rate limiters for StoryForge.

Provides two implementations behind a common interface:
  - RedisRateLimiter:   sliding-window via Redis sorted sets; automatically
                        falls back to in-memory when Redis is unreachable.
  - InMemoryRateLimiter: clean extraction of the existing per-IP approach.

Use get_rate_limiter() to obtain a singleton that auto-selects the best
available backend based on the REDIS_URL environment variable.

Module layout:
  rate_limiter_redis.py       — this file: public API + factory
  _rate_limiter_inmemory.py   — InMemoryRateLimiter
  _rate_limiter_redis_impl.py — RedisRateLimiter
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Re-export base class for callers that type-annotate against it
# ---------------------------------------------------------------------------

from services._rate_limiter_base import RateLimiterBase  # noqa: E402

# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------

from services._rate_limiter_inmemory import InMemoryRateLimiter      # noqa: E402
from services._rate_limiter_redis_impl import RedisRateLimiter        # noqa: E402


# ---------------------------------------------------------------------------
# Factory (singleton)
# ---------------------------------------------------------------------------

_instance: Optional[RateLimiterBase] = None
_factory_lock = threading.Lock()


def get_rate_limiter() -> RateLimiterBase:
    """Return the singleton rate limiter.

    Selection:
      REDIS_URL set → RedisRateLimiter (auto-fallback to in-memory if unreachable)
      Otherwise     → InMemoryRateLimiter
    """
    global _instance
    if _instance is not None:
        return _instance
    with _factory_lock:
        if _instance is not None:
            return _instance
        redis_url = os.environ.get("REDIS_URL", "").strip()
        if redis_url:
            logger.info("rate_limiter: REDIS_URL set — attempting RedisRateLimiter")
            _instance = RedisRateLimiter(redis_url)
        else:
            logger.info("rate_limiter: no REDIS_URL — using InMemoryRateLimiter")
            _instance = InMemoryRateLimiter()
    return _instance


__all__ = ["RateLimiterBase", "InMemoryRateLimiter", "RedisRateLimiter", "get_rate_limiter"]
