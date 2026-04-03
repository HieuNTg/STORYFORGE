"""Database connection manager for PostgreSQL.

Async SQLAlchemy 2.0+ engine and session management.
All functions degrade gracefully when DATABASE_URL is not set.
"""

from __future__ import annotations

import logging
import os
import threading
import warnings
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports — only pulled in when DATABASE_URL is actually set
# ---------------------------------------------------------------------------
try:
    from sqlalchemy.ext.asyncio import (
        AsyncEngine,
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )
    _SQLA_AVAILABLE = True
except ImportError:
    _SQLA_AVAILABLE = False
    AsyncEngine = None  # type: ignore[assignment,misc]
    AsyncSession = None  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# Thread-safe singleton state
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_engine: Optional["AsyncEngine"] = None  # noqa: F821
_session_factory: Optional["async_sessionmaker[AsyncSession]"] = None  # noqa: F821


def _get_database_url() -> Optional[str]:
    """Return DATABASE_URL from environment, or None."""
    return os.environ.get("DATABASE_URL") or None


def _setup_pool_metrics(engine: "AsyncEngine") -> None:  # noqa: F821
    """Attach SQLAlchemy pool event listeners for observability.

    Logs pool checkout/checkin events at DEBUG level so pool exhaustion
    issues can be diagnosed from structured logs.
    """
    from sqlalchemy import event

    sync_engine = engine.sync_engine

    @event.listens_for(sync_engine, "checkout")
    def _on_checkout(dbapi_conn, connection_record, connection_proxy):
        pool = sync_engine.pool
        logger.debug(
            "DB pool checkout: size=%d, checked_in=%d, overflow=%d",
            pool.size(), pool.checkedin(), pool.overflow(),
        )

    @event.listens_for(sync_engine, "checkin")
    def _on_checkin(dbapi_conn, connection_record):
        pool = sync_engine.pool
        logger.debug(
            "DB pool checkin: size=%d, checked_in=%d, overflow=%d",
            pool.size(), pool.checkedin(), pool.overflow(),
        )


def _warn_no_db() -> None:
    warnings.warn(
        "DATABASE_URL is not set — database operations are no-ops.",
        RuntimeWarning,
        stacklevel=3,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_engine() -> Optional["AsyncEngine"]:  # noqa: F821
    """Return (or lazily create) the async engine singleton.

    Returns None if DATABASE_URL is not configured.
    """
    global _engine, _session_factory

    url = _get_database_url()
    if not url:
        _warn_no_db()
        return None

    if not _SQLA_AVAILABLE:
        logger.error("sqlalchemy[asyncio] not installed — cannot create engine.")
        return None

    if _engine is None:
        with _lock:
            # Double-checked locking
            if _engine is None:
                logger.info("Creating async SQLAlchemy engine for PostgreSQL.")
                _engine = create_async_engine(
                    url,
                    echo=os.environ.get("DB_ECHO", "").lower() in ("1", "true"),
                    pool_size=int(os.environ.get("DB_POOL_SIZE", "5")),
                    max_overflow=int(os.environ.get("DB_MAX_OVERFLOW", "10")),
                    pool_pre_ping=True,
                )
                _setup_pool_metrics(_engine)
                _session_factory = async_sessionmaker(
                    _engine,
                    class_=AsyncSession,
                    expire_on_commit=False,
                )
    return _engine


@asynccontextmanager
async def get_session() -> AsyncIterator[Optional["AsyncSession"]]:  # noqa: F821
    """Async context manager yielding an AsyncSession.

    Yields None if DATABASE_URL is not configured or engine unavailable.

    Usage::

        async with get_session() as session:
            if session is None:
                return  # DB not available
            result = await session.execute(...)
    """
    engine = get_engine()
    if engine is None or _session_factory is None:
        yield None
        return

    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> bool:
    """Create all tables defined in db_models if they don't exist.

    Returns True on success, False if DATABASE_URL is not set or error occurs.
    """
    engine = get_engine()
    if engine is None:
        logger.warning("init_db: DATABASE_URL not set — skipping table creation.")
        return False

    try:
        # Import here to avoid circular imports at module load time
        from models.db_models import Base  # noqa: PLC0415

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("init_db: all tables created / verified.")
        return True
    except Exception as exc:
        logger.error("init_db failed: %s", exc, exc_info=True)
        return False


async def close_db() -> None:
    """Dispose the engine and reset singleton state.

    Safe to call even if DATABASE_URL was never set.
    """
    global _engine, _session_factory

    with _lock:
        if _engine is not None:
            try:
                await _engine.dispose()
                logger.info("close_db: engine disposed.")
            except Exception as exc:
                logger.error("close_db error: %s", exc, exc_info=True)
            finally:
                _engine = None
                _session_factory = None
