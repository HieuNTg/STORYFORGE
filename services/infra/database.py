"""Async database manager for the local SQLite store.

Async SQLAlchemy 2.0+ engine and session management on ``aiosqlite``. The
database file is located by :mod:`services.infra.db_paths`
(``STORYFORGE_DB_PATH`` or ``data/storyforge.db``), so an engine is always
available.
"""

from __future__ import annotations

import logging
import os
import threading
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from services.infra.db_paths import async_url, ensure_db_dir

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thread-safe singleton state
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_engine: Optional[AsyncEngine] = None
_engine_url: Optional[str] = None
_session_factory: Optional["async_sessionmaker[AsyncSession]"] = None

# Stateless engine-setup helpers live in _database_setup; re-imported here so
# existing services.infra.database.<name> references and patch targets work.
from services.infra._database_setup import (  # noqa: E402
    _setup_pool_metrics,
    _setup_sqlite_pragmas,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_engine() -> AsyncEngine:
    """Return (or lazily create) the async engine singleton.

    The engine is rebuilt when ``STORYFORGE_DB_PATH`` points somewhere new, so
    a redirected path never keeps writing to the previous file.
    """
    global _engine, _engine_url, _session_factory

    url = async_url()
    if _engine is None or _engine_url != url:
        with _lock:
            # Double-checked locking
            if _engine is None or _engine_url != url:
                logger.info("Creating async SQLAlchemy engine for %s", url)
                ensure_db_dir()
                engine = create_async_engine(
                    url,
                    echo=os.environ.get("DB_ECHO", "").lower() in ("1", "true"),
                    pool_pre_ping=True,
                )
                _setup_sqlite_pragmas(engine)
                _setup_pool_metrics(engine)
                _session_factory = async_sessionmaker(
                    engine,
                    class_=AsyncSession,
                    expire_on_commit=False,
                )
                _engine = engine
                _engine_url = url
    return _engine


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Async context manager yielding an AsyncSession.

    Commits on clean exit and rolls back on error.

    Usage::

        async with get_session() as session:
            result = await session.execute(...)
    """
    get_engine()
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def transaction() -> AsyncIterator[AsyncSession]:
    """Async context manager yielding an AsyncSession with an explicit transaction.

    Guarantees atomicity for multi-step write operations: all statements either
    commit together or roll back entirely on any exception, preventing orphaned
    records from partial writes (e.g. story creation followed by chapter inserts).

    Usage::

        async with transaction() as session:
            session.add(story)
            session.add(chapter)   # both commit or both roll back
    """
    get_engine()
    async with _session_factory() as session:
        async with session.begin():
            try:
                yield session
            except Exception:
                # session.begin() rolls back automatically on __aexit__ with exc
                raise


async def init_db() -> bool:
    """Create all tables defined in db_models if they don't exist.

    Returns True on success, False if an error occurs.
    """
    try:
        engine = get_engine()
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

    Safe to call even if no engine was ever created.
    """
    global _engine, _engine_url, _session_factory

    engine_to_dispose = None
    with _lock:
        if _engine is not None:
            engine_to_dispose = _engine
            _engine = None
            _engine_url = None
            _session_factory = None

    if engine_to_dispose is not None:
        try:
            await engine_to_dispose.dispose()
            logger.info("close_db: engine disposed.")
        except Exception as exc:
            logger.error("close_db error: %s", exc, exc_info=True)
