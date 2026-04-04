"""LLM response cache — dual-backend: Redis (production) or SQLite (local)."""

import hashlib
import json
import os
import logging
import threading
import time

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
# Deployment safety check
# ---------------------------------------------------------------------------

def _check_deployment_safety() -> None:
    """Fail fast when cache config is unsafe for the deployment context.

    Checks:
    1. NUM_WORKERS > 1 + no REDIS_URL → hard RuntimeError (data corruption risk).
       Applies to ALL environments — not just production.
    """
    num_workers_raw = os.environ.get("NUM_WORKERS", "").strip()
    try:
        num_workers = int(num_workers_raw) if num_workers_raw else 1
    except ValueError:
        num_workers = 1

    # Also check WEB_CONCURRENCY (uvicorn/gunicorn standard var)
    if num_workers <= 1:
        web_concurrency_raw = os.environ.get("WEB_CONCURRENCY", "").strip()
        try:
            num_workers = int(web_concurrency_raw) if web_concurrency_raw else num_workers
        except ValueError:
            pass

    redis_url = os.environ.get("REDIS_URL", "").strip()

    # Hard fail for multi-process without Redis — applies regardless of environment.
    # SQLite WAL mode is thread-safe but NOT process-safe; gunicorn workers are processes.
    if num_workers > 1 and not redis_url:
        msg = (
            f"STORYFORGE CACHE SAFETY: NUM_WORKERS={num_workers} (or WEB_CONCURRENCY) "
            "but no REDIS_URL. SQLite does NOT support safe concurrent multi-process writes — "
            "set REDIS_URL to switch to Redis."
        )
        logger.critical(msg)
        raise RuntimeError(msg)


_check_deployment_safety()


# ---------------------------------------------------------------------------
# SQLite backend
# ---------------------------------------------------------------------------

class LLMCache:
    """Cache LLM responses in SQLite. Thread-safe via thread-local connections + WAL mode.

    Suitable for local/single-process use only. For multi-process production
    deployments use RedisCache (or create_cache() factory which auto-selects).
    """

    def __init__(self, db_path: str = "data/llm_cache.db", ttl_days: int = 7):
        import sqlite3
        self._sqlite3 = sqlite3
        if ttl_days < 1:
            logger.warning(f"Cache TTL {ttl_days} days invalid, defaulting to 7")
            ttl_days = 7
        self._local = threading.local()
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
            logger.error("Cache put failed (OperationalError — possible DB corruption): %s", e)
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


# ---------------------------------------------------------------------------
# Redis backend
# ---------------------------------------------------------------------------

class RedisCache:
    """Cache LLM responses in Redis. Same interface as LLMCache.

    Falls back gracefully on connection errors — get() returns None,
    put() silently skips.  Requires redis>=4.0 (redis-py).
    """

    _KEY_PREFIX = "llm_cache:"

    def __init__(self, redis_url: str, ttl_days: int = 7):
        if not _REDIS_AVAILABLE:
            raise RuntimeError(
                "redis package is not installed. Run: pip install redis"
            )
        if ttl_days < 1:
            logger.warning(f"Cache TTL {ttl_days} days invalid, defaulting to 7")
            ttl_days = 7
        self.ttl_seconds = ttl_days * 86400
        self._hits = 0
        self._misses = 0
        self._counter_lock = threading.Lock()
        self._client = _redis_lib.from_url(redis_url, decode_responses=True)
        # Fail fast: verify connectivity at startup — do not silently degrade.
        # A Redis URL that cannot be reached at boot will corrupt data silently.
        try:
            self._client.ping()
        except Exception as e:
            logger.error(
                "RedisCache startup ping failed for %s: %s",
                redis_url.split("@")[-1],
                e,
            )
            raise RuntimeError(
                f"Redis unreachable at startup ({redis_url.split('@')[-1]}): {e}"
            ) from e
        logger.info("RedisCache connected: %s", redis_url.split("@")[-1])

    def _make_key(self, **params) -> str:
        raw = json.dumps(params, sort_keys=True, ensure_ascii=False)
        h = hashlib.sha256(raw.encode()).hexdigest()
        return f"{self._KEY_PREFIX}{h}"

    def get(self, **params) -> "str | None":
        try:
            val = self._client.get(self._make_key(**params))
            if val is not None:
                logger.debug("Cache hit (redis)")
                with self._counter_lock:
                    self._hits += 1
                return val
            with self._counter_lock:
                self._misses += 1
            return None
        except Exception as e:
            logger.warning("RedisCache get error: %s", e)
            with self._counter_lock:
                self._misses += 1
            return None

    def put(self, response: str, **params) -> None:
        try:
            self._client.setex(self._make_key(**params), self.ttl_seconds, response)
        except Exception as e:
            logger.warning("RedisCache put error: %s", e)

    def evict_expired(self) -> int:
        # Redis handles TTL-based eviction natively; nothing to do here.
        return 0

    def stats(self) -> dict:
        total_req = self._hits + self._misses
        hit_rate = (self._hits / total_req * 100) if total_req > 0 else 0.0
        try:
            info = self._client.info("memory")
            used_mb = round(info.get("used_memory", 0) / 1024 / 1024, 2)
        except Exception:
            used_mb = None
        return {
            "backend": "redis",
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_pct": round(hit_rate, 1),
            "redis_used_memory_mb": used_mb,
        }

    def clear(self) -> None:
        try:
            keys = self._client.keys(f"{self._KEY_PREFIX}*")
            if keys:
                self._client.delete(*keys)
            logger.info("RedisCache cleared %d keys", len(keys))
        except Exception as e:
            logger.warning("RedisCache clear error: %s", e)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_cache(
    redis_url: str = "",
    db_path: str = "data/llm_cache.db",
    ttl_days: int = 7,
) -> "LLMCache | RedisCache":
    """Return a RedisCache if redis_url is set, otherwise an LLMCache (SQLite).

    Falls back to SQLite if redis package is unavailable or connection fails.
    """
    url = redis_url or os.environ.get("REDIS_URL", "").strip()
    if url:
        if not _REDIS_AVAILABLE:
            raise RuntimeError(
                "REDIS_URL is set but redis package is not installed. Run: pip install redis"
            )
        # Let RedisCache.__init__ raise on connectivity failure — no silent SQLite fallback
        # when Redis was explicitly configured.
        return RedisCache(redis_url=url, ttl_days=ttl_days)
    return LLMCache(db_path=db_path, ttl_days=ttl_days)


# ---------------------------------------------------------------------------
# Module-level singleton (used by existing callers)
# ---------------------------------------------------------------------------
_cache_instance: "LLMCache | RedisCache | None" = None
_cache_lock = threading.Lock()


def get_cache() -> "LLMCache | RedisCache":
    """Return the module-level singleton cache, creating it on first call."""
    global _cache_instance
    if _cache_instance is None:
        with _cache_lock:
            if _cache_instance is None:
                _cache_instance = create_cache()
    return _cache_instance
