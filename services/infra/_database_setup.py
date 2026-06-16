"""Stateless engine-setup helpers for the database manager.

Internal module for ``database``: DATABASE_URL resolution, the SQLite pragma and
pool-metrics event listeners, and the no-DB warning. None of these touch the
engine/session singleton state, which stays in ``database``. The helpers are
imported back into ``database`` so existing ``services.infra.database.<name>``
references and patch targets keep working.
"""

from __future__ import annotations

import logging
import os
import warnings
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


def _get_database_url() -> Optional[str]:
    """Return DATABASE_URL from environment, or None."""
    return os.environ.get("DATABASE_URL") or None


def _setup_sqlite_pragmas(engine: "AsyncEngine") -> None:  # noqa: F821
    """Set WAL mode + performance pragmas on every new SQLite connection."""
    from sqlalchemy import event

    sync_engine = engine.sync_engine
    db_url = str(sync_engine.url)
    if "sqlite" not in db_url:
        return

    @event.listens_for(sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


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
            pool.size(),
            pool.checkedin(),
            pool.overflow(),
        )

    @event.listens_for(sync_engine, "checkin")
    def _on_checkin(dbapi_conn, connection_record):
        pool = sync_engine.pool
        logger.debug(
            "DB pool checkin: size=%d, checked_in=%d, overflow=%d",
            pool.size(),
            pool.checkedin(),
            pool.overflow(),
        )


def _warn_no_db() -> None:
    warnings.warn(
        "DATABASE_URL is not set — database operations are no-ops.",
        RuntimeWarning,
        stacklevel=3,
    )
