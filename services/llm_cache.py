"""SQLite cache cho LLM responses."""

import hashlib
import json
import sqlite3
import time
import os
import logging
import threading
import warnings

logger = logging.getLogger(__name__)


def _check_deployment_safety() -> None:
    """Emit warnings when the cache configuration is unsafe for the deployment context.

    Called once at module import time so operators see the warnings in startup logs
    before any request is served.

    Checks performed:
    1. NUM_WORKERS > 1 with SQLite backend → CRITICAL (data corruption risk).
    2. STORYFORGE_ENV=production with no REDIS_URL → WARNING (Redis recommended).
    """
    num_workers_raw = os.environ.get("NUM_WORKERS", "").strip()
    try:
        num_workers = int(num_workers_raw) if num_workers_raw else 1
    except ValueError:
        num_workers = 1

    redis_url = os.environ.get("REDIS_URL", "").strip()
    storyforge_env = os.environ.get("STORYFORGE_ENV", "").strip().lower()

    # Check 1: multi-process + SQLite = corruption / cost explosion risk
    if num_workers > 1:
        msg = (
            f"STORYFORGE CACHE SAFETY: NUM_WORKERS={num_workers} but the LLM cache "
            "backend is SQLite. SQLite does NOT support safe concurrent multi-process "
            "writes — you will experience database lock errors, duplicate LLM calls, "
            "and potential data corruption. Set REDIS_URL to switch to Redis, or "
            "run with NUM_WORKERS=1."
        )
        logger.critical(msg)
        warnings.warn(msg, RuntimeWarning, stacklevel=2)

    # Check 2: production environment without Redis
    if storyforge_env == "production" and not redis_url:
        msg = (
            "STORYFORGE CACHE: Running in production (STORYFORGE_ENV=production) "
            "without a Redis cache backend. Set REDIS_URL to a Redis instance for "
            "reliable shared caching across workers and restarts."
        )
        logger.warning(msg)


_check_deployment_safety()


class LLMCache:
    """Cache LLM responses trong SQLite. Thread-safe via thread-local connections + WAL mode.

    CONCURRENCY LIMITATION (multi-user / multi-process):
    WAL (Write-Ahead Logging) mode allows concurrent reads alongside one writer,
    but SQLite still serializes all writes. In a single-process, multi-threaded
    setup this is acceptable. However, in a multi-process deployment (e.g. multiple
    uvicorn workers or gunicorn workers), each process maintains its own WAL reader
    state and write lock contention increases significantly. SQLite is NOT suitable
    as a shared cache across multiple processes at high concurrency.

    For multi-user production deployments, replace this cache with Redis or another
    shared in-memory store that supports true concurrent multi-process access.
    """

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
        try:
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, response, created_at) VALUES (?,?,?)",
                (key, response, time.time()),
            )
            conn.commit()
        except sqlite3.OperationalError as e:
            # Handle concurrent write contention (database locked)
            logger.warning(f"Cache put failed (concurrent write): {e}")
        except sqlite3.Error as e:
            logger.warning(f"Cache put failed: {e}")

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
