"""Branch persistence — in-memory session store for the local single process."""

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory backend
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
                sid
                for sid in self._sessions
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
# Factory
# ---------------------------------------------------------------------------


def create_branch_store(
    max_sessions: int = 50,
    ttl_seconds: int = 86400,
) -> InMemoryBranchStore:
    """Return a fresh in-memory branch session store."""
    return InMemoryBranchStore(max_sessions=max_sessions, ttl_seconds=ttl_seconds)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_store_instance: Optional[InMemoryBranchStore] = None
_store_lock = threading.Lock()


def get_branch_store() -> InMemoryBranchStore:
    """Return the module-level singleton store, creating it on first call."""
    global _store_instance
    if _store_instance is None:
        with _store_lock:
            if _store_instance is None:
                _store_instance = create_branch_store()
    return _store_instance
