"""SQLite cache cho LLM responses."""

import hashlib
import json
import sqlite3
import time
import os
import logging

logger = logging.getLogger(__name__)


class LLMCache:
    """Cache LLM responses trong SQLite. Thread-safe via connection-per-call."""

    def __init__(self, db_path="data/llm_cache.db", ttl_days=7):
        self.db_path = db_path
        self.ttl = ttl_days * 86400
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                response TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    def _make_key(self, **params) -> str:
        raw = json.dumps(params, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, **params) -> str | None:
        key = self._make_key(**params)
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT response, created_at FROM cache WHERE key=?", (key,)
        ).fetchone()
        conn.close()
        if row and (time.time() - row[1]) < self.ttl:
            logger.debug("Cache hit")
            return row[0]
        return None

    def put(self, response: str, **params):
        key = self._make_key(**params)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO cache (key, response, created_at) VALUES (?,?,?)",
            (key, response, time.time()),
        )
        conn.commit()
        conn.close()

    def evict_expired(self) -> int:
        """Remove expired entries. Returns number of entries removed."""
        cutoff = time.time() - self.ttl
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("DELETE FROM cache WHERE created_at < ?", (cutoff,))
        removed = cursor.rowcount
        conn.commit()
        conn.close()
        if removed:
            logger.info(f"Cache evicted {removed} expired entries")
        return removed

    def stats(self) -> dict:
        """Return cache statistics."""
        conn = sqlite3.connect(self.db_path)
        total = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        cutoff = time.time() - self.ttl
        valid = conn.execute("SELECT COUNT(*) FROM cache WHERE created_at >= ?", (cutoff,)).fetchone()[0]
        conn.close()
        return {"total": total, "valid": valid, "expired": total - valid}

    def clear(self):
        """Remove all cache entries."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM cache")
        conn.commit()
        conn.close()
        logger.info("Cache cleared")
