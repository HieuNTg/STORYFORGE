"""LLM response cache backed by SQLite (``data/llm_cache.db``)."""

import hashlib
import json
import os
import logging
import threading
import time

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = "data/llm_cache.db"


def default_db_path() -> str:
    """Where the SQLite cache lives, overridable via STORYFORGE_LLM_CACHE_DB.

    Read per call rather than at import so the test suite can redirect it
    regardless of import order. Without a redirect, tests share the developer's
    real cache: they always wrote to it, and once the cache key was fixed so
    reads actually hit, one test could be served another's response.
    """
    return os.environ.get("STORYFORGE_LLM_CACHE_DB") or _DEFAULT_DB_PATH


# ---------------------------------------------------------------------------
# SQLite backend
# ---------------------------------------------------------------------------


class LLMCache:
    """Cache LLM responses in SQLite. Thread-safe via thread-local connections + WAL mode.

    StoryForge runs as a single local process; SQLite WAL mode covers it.
    """

    def __init__(self, db_path: str | None = None, ttl_days: int = 7):
        import sqlite3

        self._sqlite3 = sqlite3
        if ttl_days < 1:
            logger.warning(f"Cache TTL {ttl_days} days invalid, defaulting to 7")
            ttl_days = 7
        self._local = threading.local()
        db_path = db_path or default_db_path()
        self.db_path = db_path
        self.ttl = ttl_days * 86400
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_db()
        self._hits = 0
        self._misses = 0
        self._counter_lock = threading.Lock()
        self._call_count = 0

    def _get_conn(self):
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = self._sqlite3.connect(self.db_path, timeout=5.0)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
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

    def get(self, **params) -> "str | None":
        with self._counter_lock:
            self._call_count += 1
            should_evict = self._call_count % 100 == 0
        if should_evict:
            try:
                self.evict_expired()
            except Exception:
                logger.debug("Cache eviction failed", exc_info=True)

        key = self._make_key(**params)
        conn = self._get_conn()
        row = conn.execute(
            "SELECT response, created_at FROM cache WHERE key=?", (key,)
        ).fetchone()
        if row and (time.time() - row[1]) < self.ttl:
            logger.debug("Cache hit (sqlite)")
            with self._counter_lock:
                self._hits += 1
            return row[0]
        with self._counter_lock:
            self._misses += 1
        return None

    def put(self, response: str, **params) -> None:
        import sqlite3

        key = self._make_key(**params)
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, response, created_at) VALUES (?,?,?)",
                (key, response, time.time()),
            )
            conn.commit()
        except sqlite3.OperationalError as e:
            logger.error(
                "Cache put failed (OperationalError — possible DB corruption): %s", e
            )
            raise
        except sqlite3.Error as e:
            logger.error("Cache put failed: %s", e)
            raise

    def evict_expired(self) -> int:
        cutoff = time.time() - self.ttl
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM cache WHERE created_at < ?", (cutoff,))
        removed = cursor.rowcount
        conn.commit()
        if removed:
            logger.info(f"Cache evicted {removed} expired entries")
        return removed

    def stats(self) -> dict:
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        cutoff = time.time() - self.ttl
        valid = conn.execute(
            "SELECT COUNT(*) FROM cache WHERE created_at >= ?", (cutoff,)
        ).fetchone()[0]
        total_req = self._hits + self._misses
        hit_rate = (self._hits / total_req * 100) if total_req > 0 else 0.0
        return {
            "backend": "sqlite",
            "total_entries": total,
            "valid_entries": valid,
            "expired": total - valid,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_pct": round(hit_rate, 1),
        }

    def clear(self) -> None:
        conn = self._get_conn()
        conn.execute("DELETE FROM cache")
        conn.commit()
        logger.info("Cache cleared")

