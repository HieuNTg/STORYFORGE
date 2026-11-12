"""Stateless engine-setup helpers for the database manager.

Internal module for ``database``: the SQLite pragma and pool-metrics event
listeners. None of these touch the engine/session singleton state, which stays
in ``database``. The helpers are imported back into ``database`` so existing
``services.infra.database.<name>`` references and patch targets keep working.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


def _setup_sqlite_pragmas(engine: "AsyncEngine") -> None:  # noqa: F821
    """Set WAL mode + performance pragmas on every new SQLite connection."""
    from sqlalchemy import event

    from services.infra.db_paths import set_sqlite_pragmas

    event.listen(engine.sync_engine, "connect", set_sqlite_pragmas)


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

