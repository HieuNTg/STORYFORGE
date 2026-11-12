"""Rate-limit check backend for middleware/rate_limiter.py.

A per-IP fixed-window counter held in process memory. StoryForge runs as a
single local process, so no shared store is needed.

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
# In-memory backend
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

