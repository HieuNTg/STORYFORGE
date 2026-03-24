"""SQLite cache cho LLM responses."""

import hashlib
import json
import sqlite3
import time
import os
import logging
import threading

logger = logging.getLogger(__name__)


class LLMCache:
    """Cache LLM responses trong SQLite. Thread-safe via thread-local connections + WAL mode."""

    def __init__(self, db_path="data/llm_cache.db", ttl_days=7):
        # Issue #4: validate TTL
        if ttl_days < 1:
            logger.warning(f"Cache TTL {ttl_days} days invalid, defaulting to 7")
            ttl_days = 7
        self._local = threading.local()
        self.db_path = db_path
        self.ttl = ttl_days * 86400
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()
        self._hits = 0
        self._misses = 0
        # Issue #7: lock for counter increments
        self._counter_lock = threading.Lock()
        # Issue #6: call counter for periodic eviction
        self._call_count = 0

    def _get_conn(self) -> sqlite3.Connection:
        """Issue #5: thread-local connection with WAL mode."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, timeout=5.0)
            self._local.conn.execute('PRAGMA journal_mode=WAL')
            self._local.conn.execute('PRAGMA synchronous=NORMAL')
        return self._local.conn

    def _init_db(self):
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                response TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        conn.commit()

    def _make_key(self, **params) -> str:
        raw = json.dumps(params, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, **params) -> str | None:
        # Issue #6: periodic eviction every 100 calls
        with self._counter_lock:
            self._call_count += 1
            should_evict = self._call_count % 100 == 0
        if should_evict:
            try:
                self.evict_expired()
            except Exception:
                pass

        key = self._make_key(**params)
        conn = self._get_conn()
        row = conn.execute(
            "SELECT response, created_at FROM cache WHERE key=?", (key,)
        ).fetchone()

        if row and (time.time() - row[1]) < self.ttl:
            logger.debug("Cache hit")
            # Issue #7: thread-safe counter increment
            with self._counter_lock:
                self._hits += 1
            return row[0]

        # Issue #7: thread-safe counter increment
        with self._counter_lock:
            self._misses += 1
        return None

    def put(self, response: str, **params):
        key = self._make_key(**params)
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO cache (key, response, created_at) VALUES (?,?,?)",
            (key, response, time.time()),
        )
        conn.commit()

    def evict_expired(self) -> int:
        """Remove expired entries. Returns number of entries removed."""
        cutoff = time.time() - self.ttl
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM cache WHERE created_at < ?", (cutoff,))
        removed = cursor.rowcount
        conn.commit()
        if removed:
            logger.info(f"Cache evicted {removed} expired entries")
        return removed

    def stats(self) -> dict:
        """Return cache statistics including hit rate."""
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        cutoff = time.time() - self.ttl
        valid = conn.execute("SELECT COUNT(*) FROM cache WHERE created_at >= ?", (cutoff,)).fetchone()[0]
        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0.0
        return {
            "total_entries": total,
            "valid_entries": valid,
            "expired": total - valid,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_pct": round(hit_rate, 1),
        }

    def clear(self):
        """Remove all cache entries."""
        conn = self._get_conn()
        conn.execute("DELETE FROM cache")
        conn.commit()
        logger.info("Cache cleared")
