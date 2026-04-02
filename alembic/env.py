"""Alembic environment configuration for StoryForge.

Supports:
- Offline (sync) mode for generating SQL scripts
- Online (async) mode using asyncpg for running migrations directly

DATABASE_URL must use the asyncpg driver, e.g.:
    postgresql+asyncpg://user:pass@host/dbname

For sync/offline use the psycopg2 driver is substituted automatically.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

# ---------------------------------------------------------------------------
# Register all ORM models so their metadata is visible to Alembic
# ---------------------------------------------------------------------------
from models.db_models import Base  # noqa: E402 — must be after sys.path setup

# ---------------------------------------------------------------------------
# Alembic Config object (gives access to alembic.ini values)
# ---------------------------------------------------------------------------
config = context.config

# Apply logging config from alembic.ini (if present)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

# Metadata object Alembic uses to generate / compare schemas
target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Resolve DATABASE_URL
# ---------------------------------------------------------------------------

def _get_url() -> str:
    """Return async DATABASE_URL from env, falling back to alembic.ini."""
    return os.environ.get("DATABASE_URL") or config.get_main_option("sqlalchemy.url", "")


def _sync_url(async_url: str) -> str:
    """Convert asyncpg URL to psycopg2 for offline/sync mode."""
    return re.sub(r"postgresql\+asyncpg://", "postgresql+psycopg2://", async_url)


# ---------------------------------------------------------------------------
# Offline migration mode (generates SQL without a live DB connection)
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """Emit migration SQL to stdout / file without connecting to the database."""
    url = _sync_url(_get_url())
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online async migration mode (connects and runs migrations directly)
# ---------------------------------------------------------------------------

def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create async engine and run migrations within a sync-compatible wrapper."""
    connectable = create_async_engine(
        _get_url(),
        poolclass=pool.NullPool,  # Alembic does not need a persistent pool
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
