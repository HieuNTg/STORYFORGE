"""InMemoryRateLimiter — tumbling-window in-process rate limiter.

Internal module; public API is via services.rate_limiter_redis.
"""

from __future__ import annotations

import threading
import time

from services._rate_limiter_base import RateLimiterBase


class InMemoryRateLimiter(RateLimiterBase):
    """Sliding-window rate limiter backed by an in-process dict.

    Uses a fixed tumbling window: counter resets when window_seconds elapses.
    Thread-safe via a per-instance lock.  Suitable for single-process
    deployments; state is lost on process restart.
    """

    def __init__(self) -> None:
        # key -> [count, window_start_monotonic]
        self._state: dict[str, list] = {}
        self._lock = threading.Lock()

    def is_allowed(self, key: str, limit: int, window_seconds: int) -> bool:
        """Return True if under limit; False if limit reached."""
        now = time.monotonic()
        with self._lock:
            entry = self._state.get(key)
            if entry is None or (now - entry[1]) >= window_seconds:
                self._state[key] = [1, now]
                return True
            if entry[0] < limit:
                entry[0] += 1
                return True
            return False

    def get_remaining(self, key: str, limit: int, window_seconds: int) -> int:
        """Return requests remaining in the current window."""
        now = time.monotonic()
        with self._lock:
            entry = self._state.get(key)
            if entry is None or (now - entry[1]) >= window_seconds:
                return limit
            return max(0, limit - entry[0])
