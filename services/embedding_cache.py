"""SQLite-backed embedding cache (Sprint 2, P2).

Implements the `_CacheBackend` Protocol from `services/embedding_service.py`.

Key design:
- Separate SQLite file (`data/embedding_cache.db`) — not the main PostgreSQL DB.
  The main DB is async PostgreSQL; embedding cache is CPU-bound sync SQLite.
  Mirrors the pattern used by `services/llm_cache.py`.
- Key: sha256(model_id + NFC(text)) — computed by `embedding_service.cache_key()`.
  This module only stores/retrieves; normalisation happens in the service.
- Value: float32 little-endian bytes of the embedding vector.
- Idempotent insert via `INSERT OR IGNORE`.
- Thread-safe via thread-local connections + WAL mode.

P2 scope: storage backend only. The service's `attach_cache()` hook wires it at startup.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = os.path.join("data", "embedding_cache.db")


# ---------------------------------------------------------------------------
# ORM-style table DDL (kept in this module; also mirrored in models/db_models.py)
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS embedding_cache (
    key        TEXT        NOT NULL PRIMARY KEY,
    model_id   TEXT        NOT NULL,
    dim        INTEGER     NOT NULL,
    vec        BLOB        NOT NULL,
    created_at TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_embedding_cache_model_id
    ON embedding_cache (model_id);
"""


# ---------------------------------------------------------------------------
# Cache implementation
# ---------------------------------------------------------------------------


class EmbeddingCache:
    """SQLite-backed embedding cache implementing the `_CacheBackend` Protocol.

    Thread-safe: each thread gets its own connection (WAL mode).
    The `key` argument is always the pre-computed sha256 hex string from
    `embedding_service.cache_key(model_id, text)` — we do NOT recompute it here.
    """

    def __init__(self, db_path: str = _DEFAULT_DB_PATH) -> None:
        self._db_path = db_path
        self._local = threading.local()
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        # Initialise schema on the calling thread's connection.
        self._init_db()

    # -- connection management ----------------------------------------------

    def _conn(self) -> sqlite3.Connection:
        """Return thread-local connection, creating it if needed."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self._db_path, timeout=10.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = conn
        return self._local.conn

    def _init_db(self) -> None:
        conn = self._conn()
        conn.executescript(_DDL)
        conn.commit()

    # -- _CacheBackend Protocol interface -----------------------------------

    def get(self, key: str) -> bytes | None:
        """Return stored float32 LE bytes for `key`, or None on miss."""
        row = self._conn().execute(
            "SELECT vec FROM embedding_cache WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None

    def put(self, key: str, model_id: str, vec_bytes: bytes) -> None:
        """Persist `vec_bytes` under `key`. Idempotent — duplicate keys are ignored."""
        import numpy as np

        # Derive dim from byte length (float32 = 4 bytes each)
        dim = len(vec_bytes) // 4
        conn = self._conn()
        conn.execute(
            "INSERT OR IGNORE INTO embedding_cache (key, model_id, dim, vec, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (key, model_id, dim, vec_bytes, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()

    # -- Bulk helpers (used by embed_batch path internally) -----------------

    def bulk_get(self, keys: list[str]) -> dict[str, bytes]:
        """Fetch multiple keys in a single query. Returns {key: vec_bytes} for hits."""
        if not keys:
            return {}
        placeholders = ",".join("?" * len(keys))
        rows = self._conn().execute(
            f"SELECT key, vec FROM embedding_cache WHERE key IN ({placeholders})",
            keys,
        ).fetchall()
        return {row[0]: row[1] for row in rows}

    # -- Diagnostics -------------------------------------------------------

    def stats(self) -> dict:
        """Return row count and disk size for diagnostics."""
        conn = self._conn()
        total = conn.execute("SELECT COUNT(*) FROM embedding_cache").fetchone()[0]
        try:
            size_bytes = os.path.getsize(self._db_path)
        except OSError:
            size_bytes = 0
        return {
            "backend": "sqlite",
            "total_entries": total,
            "db_path": self._db_path,
            "db_size_bytes": size_bytes,
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_cache_instance: EmbeddingCache | None = None
_cache_lock = threading.Lock()


def get_embedding_cache(db_path: str = _DEFAULT_DB_PATH) -> EmbeddingCache:
    """Return the process-wide EmbeddingCache singleton."""
    global _cache_instance
    if _cache_instance is None:
        with _cache_lock:
            if _cache_instance is None:
                _cache_instance = EmbeddingCache(db_path=db_path)
                logger.info("EmbeddingCache initialised at %s", db_path)
    return _cache_instance


def reset_embedding_cache() -> None:
    """Test helper — drops the singleton."""
    global _cache_instance
    with _cache_lock:
        _cache_instance = None


__all__ = [
    "EmbeddingCache",
    "get_embedding_cache",
    "reset_embedding_cache",
]
