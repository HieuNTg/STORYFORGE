"""Deep health check endpoints for StoryForge.

/api/health        — shallow: always fast, returns uptime + basic service flags.
/api/health/deep   — probes each subsystem and returns per-component status.

Component checks:
  database   — executes a trivial SELECT 1 via SQLAlchemy (sync engine).
  redis      — PING via redis-py if REDIS_URL is configured.
  disk       — reports free bytes on the data directory partition.
  memory     — reports RSS and available system memory via psutil if installed,
               otherwise falls back to /proc/meminfo on Linux.
  llm        — optional HEAD/GET against the configured LLM base URL with a
               short timeout; skipped when LLM backend is not "api".
"""

from __future__ import annotations

import logging
import os
import shutil
import time
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_health_engine = None


def _check_database() -> dict[str, Any]:
    """Try a SELECT 1 via SQLAlchemy synchronous engine."""
    global _health_engine
    try:
        from sqlalchemy import create_engine, text

        if _health_engine is None:
            db_url = os.environ.get(
                "DATABASE_URL", "sqlite:///data/storyforge.db"
            )
            _health_engine = create_engine(db_url, pool_pre_ping=True, connect_args={"check_same_thread": False} if "sqlite" in db_url else {})
        with _health_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:
        logger.warning("Health/deep: database check failed: %s", exc)
        return {"status": "error", "detail": str(exc)}


def _check_redis() -> dict[str, Any]:
    """PING the configured Redis instance."""
    redis_url = os.environ.get("REDIS_URL", "")
    if not redis_url:
        return {"status": "not_configured"}
    try:
        import redis

        client = redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
        client.ping()
        return {"status": "ok"}
    except Exception as exc:
        logger.warning("Health/deep: redis check failed: %s", exc)
        return {"status": "error", "detail": str(exc)}


def _check_disk() -> dict[str, Any]:
    """Report free disk space on the data directory partition."""
    try:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        total, used, free = shutil.disk_usage(data_dir)
        return {
            "status": "ok",
            "free_bytes": free,
            "total_bytes": total,
            "used_pct": round(used / total * 100, 1),
        }
    except Exception as exc:
        logger.warning("Health/deep: disk check failed: %s", exc)
        return {"status": "error", "detail": str(exc)}


def _check_memory() -> dict[str, Any]:
    """Report memory usage via psutil (falls back to basic info if unavailable)."""
    try:
        import psutil

        vm = psutil.virtual_memory()
        return {
            "status": "ok",
            "available_bytes": vm.available,
            "total_bytes": vm.total,
            "used_pct": vm.percent,
        }
    except ImportError:
        # psutil not installed — attempt /proc/meminfo (Linux only)
        try:
            with open("/proc/meminfo") as fh:
                lines = {
                    parts[0].rstrip(":"): int(parts[1])
                    for line in fh
                    if (parts := line.split()) and len(parts) >= 2
                }
            total_kb = lines.get("MemTotal", 0)
            avail_kb = lines.get("MemAvailable", lines.get("MemFree", 0))
            used_pct = round((total_kb - avail_kb) / total_kb * 100, 1) if total_kb else 0
            return {
                "status": "ok",
                "available_bytes": avail_kb * 1024,
                "total_bytes": total_kb * 1024,
                "used_pct": used_pct,
            }
        except Exception as exc:
            return {"status": "unavailable", "detail": str(exc)}
    except Exception as exc:
        logger.warning("Health/deep: memory check failed: %s", exc)
        return {"status": "error", "detail": str(exc)}


def _check_llm() -> dict[str, Any]:
    """Optionally probe the LLM API base URL with a short timeout."""
    try:
        from config import ConfigManager

        cfg = ConfigManager()
        if cfg.llm.backend_type != "api":
            return {"status": "not_applicable", "backend": cfg.llm.backend_type}

        base_url = getattr(cfg.llm, "base_url", None) or "https://api.openai.com"
        import urllib.request

        req = urllib.request.Request(base_url, method="HEAD")
        with urllib.request.urlopen(req, timeout=3):
            pass
        return {"status": "ok", "url": base_url}
    except Exception as exc:
        # LLM reachability is optional — degrade gracefully
        return {"status": "unreachable", "detail": str(exc)}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/health/deep", summary="Deep health check")
async def deep_health() -> JSONResponse:
    """Probe every subsystem and return per-component status.

    Returns HTTP 200 when all critical components are healthy,
    HTTP 503 when any critical component (database, disk) is degraded.

    Non-critical components (redis, memory, llm) are reported but do not
    affect the top-level HTTP status code.
    """
    start = time.monotonic()

    checks: dict[str, Any] = {
        "database": _check_database(),
        "redis": _check_redis(),
        "disk": _check_disk(),
        "memory": _check_memory(),
        "llm": _check_llm(),
    }

    critical_failed = any(
        checks[k]["status"] == "error"
        for k in ("database", "disk")
    )

    overall = "degraded" if critical_failed else "ok"
    status_code = 503 if critical_failed else 200

    # Scaling readiness: Redis required for multi-instance shared state
    redis_ok = checks["redis"]["status"] == "ok"
    db_ok = checks["database"]["status"] == "ok"
    scale_ready = redis_ok and db_ok

    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall,
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "duration_ms": round((time.monotonic() - start) * 1000, 1),
            "scale_ready": scale_ready,
            "components": checks,
        },
    )
