"""Branch persistence — dual-backend: Redis (production) or in-memory (local)."""

import json
import logging
import os
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Graceful redis import
# ---------------------------------------------------------------------------
try:
    import redis as _redis_lib
    _REDIS_AVAILABLE = True
except ImportError:
    _redis_lib = None  # type: ignore[assignment]
    _REDIS_AVAILABLE = False


# ---------------------------------------------------------------------------
# In-memory backend (default, single-process)
# ---------------------------------------------------------------------------

class InMemoryBranchStore:
    """In-memory branch session store. Thread-safe via lock.

    Suitable for local/single-process use only. Sessions are lost on restart.
    """

    def __init__(self, max_sessions: int = 50, ttl_seconds: int = 86400):
        self.max_sessions = max_sessions
        self.ttl_seconds = ttl_seconds
        self._sessions: dict[str, dict] = {}
        self._timestamps: dict[str, float] = {}
        self._order: list[str] = []  # FIFO for eviction
        self._lock = threading.Lock()

    def get(self, session_id: str) -> Optional[dict]:
        """Get session data. Returns None if not found or expired."""
        with self._lock:
            if session_id not in self._sessions:
                return None
            if time.time() - self._timestamps[session_id] > self.ttl_seconds:
                self._delete_session(session_id)
                return None
            return self._sessions[session_id]

    def put(self, session_id: str, data: dict) -> None:
        """Store session data."""
        with self._lock:
            self._evict_if_needed()
            if session_id not in self._sessions:
                self._order.append(session_id)
            self._sessions[session_id] = data
            self._timestamps[session_id] = time.time()

    def delete(self, session_id: str) -> bool:
        """Delete session. Returns True if existed."""
        with self._lock:
            return self._delete_session(session_id)

    def exists(self, session_id: str) -> bool:
        """Check if session exists and is not expired."""
        return self.get(session_id) is not None

    def list_sessions(self) -> list[str]:
        """List all active session IDs."""
        with self._lock:
            now = time.time()
            return [
                sid for sid in self._sessions
                if now - self._timestamps[sid] <= self.ttl_seconds
            ]

    def _delete_session(self, session_id: str) -> bool:
        """Internal delete without lock."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            del self._timestamps[session_id]
            if session_id in self._order:
                self._order.remove(session_id)
            return True
        return False

    def _evict_if_needed(self) -> None:
        """FIFO eviction when max_sessions reached."""
        while len(self._sessions) >= self.max_sessions and self._order:
            oldest = self._order.pop(0)
            self._delete_session(oldest)


# ---------------------------------------------------------------------------
# Redis backend (production, multi-process safe)
# ---------------------------------------------------------------------------

class RedisBranchStore:
    """Redis-backed branch session store. Same interface as InMemoryBranchStore.

    Suitable for multi-process production deployments. Sessions survive restarts.
    """

    _KEY_PREFIX = "branch_session:"

    def __init__(self, redis_url: str, ttl_seconds: int = 86400):
        if not _REDIS_AVAILABLE:
            raise RuntimeError(
                "redis package is not installed. Run: pip install redis"
            )
        self.ttl_seconds = ttl_seconds
        self._client = _redis_lib.from_url(redis_url, decode_responses=True)
        # Verify connectivity
        try:
            self._client.ping()
        except Exception as e:
            logger.error("RedisBranchStore ping failed: %s", e)
            raise

    def _key(self, session_id: str) -> str:
        return f"{self._KEY_PREFIX}{session_id}"

    def get(self, session_id: str) -> Optional[dict]:
        """Get session data. Returns None if not found."""
        try:
            raw = self._client.get(self._key(session_id))
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as e:
            logger.warning("RedisBranchStore.get failed: %s", e)
            return None

    def put(self, session_id: str, data: dict) -> None:
        """Store session data with TTL."""
        try:
            self._client.setex(
                self._key(session_id),
                self.ttl_seconds,
                json.dumps(data),
            )
        except Exception as e:
            logger.warning("RedisBranchStore.put failed: %s", e)

    def delete(self, session_id: str) -> bool:
        """Delete session. Returns True if existed."""
        try:
            return self._client.delete(self._key(session_id)) > 0
        except Exception as e:
            logger.warning("RedisBranchStore.delete failed: %s", e)
            return False

    def exists(self, session_id: str) -> bool:
        """Check if session exists."""
        try:
            return self._client.exists(self._key(session_id)) > 0
        except Exception as e:
            logger.warning("RedisBranchStore.exists failed: %s", e)
            return False

    def list_sessions(self) -> list[str]:
        """List all active session IDs."""
        try:
            keys = self._client.keys(f"{self._KEY_PREFIX}*")
            return [k.replace(self._KEY_PREFIX, "") for k in keys]
        except Exception as e:
            logger.warning("RedisBranchStore.list_sessions failed: %s", e)
            return []


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_branch_store(
    redis_url: str = "",
    max_sessions: int = 50,
    ttl_seconds: int = 86400,
) -> "InMemoryBranchStore | RedisBranchStore":
    """Return a RedisBranchStore if redis_url is set, otherwise InMemoryBranchStore."""
    url = redis_url or os.environ.get("REDIS_URL", "").strip()
    if url:
        if not _REDIS_AVAILABLE:
            logger.warning(
                "REDIS_URL is set but redis package not installed. Using in-memory store."
            )
            return InMemoryBranchStore(max_sessions=max_sessions, ttl_seconds=ttl_seconds)
        try:
            return RedisBranchStore(redis_url=url, ttl_seconds=ttl_seconds)
        except Exception as e:
            logger.warning("Redis connection failed, falling back to in-memory: %s", e)
            return InMemoryBranchStore(max_sessions=max_sessions, ttl_seconds=ttl_seconds)
    return InMemoryBranchStore(max_sessions=max_sessions, ttl_seconds=ttl_seconds)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_store_instance: "InMemoryBranchStore | RedisBranchStore | None" = None
_store_lock = threading.Lock()


def get_branch_store() -> "InMemoryBranchStore | RedisBranchStore":
    """Return the module-level singleton store, creating it on first call."""
    global _store_instance
    if _store_instance is None:
        with _store_lock:
            if _store_instance is None:
                _store_instance = create_branch_store()
    return _store_instance
