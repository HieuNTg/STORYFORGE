"""Where StoryForge's SQLite database lives, and the engines that open it.

StoryForge keeps all relational data in one local SQLite file. Its location is
``STORYFORGE_DB_PATH`` when set, otherwise ``<repo>/data/storyforge.db``. The
path is read on every call so tests (and the Docker entrypoint) can redirect it
without import-order concerns.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DB_PATH = _REPO_ROOT / "data" / "storyforge.db"


def db_path() -> Path:
    """Return ``STORYFORGE_DB_PATH`` or ``<repo>/data/storyforge.db``."""
    raw = os.environ.get("STORYFORGE_DB_PATH", "").strip()
    return Path(raw) if raw else _DEFAULT_DB_PATH


def sync_url() -> str:
    """SQLAlchemy URL for the sync ``sqlite`` driver."""
    return f"sqlite:///{db_path()}"


def async_url() -> str:
    """SQLAlchemy URL for the async ``aiosqlite`` driver."""
    return f"sqlite+aiosqlite:///{db_path()}"


def ensure_db_dir() -> None:
    """Create the directory that holds the database file, if missing."""
    db_path().parent.mkdir(parents=True, exist_ok=True)


def set_sqlite_pragmas(dbapi_conn, _connection_record=None) -> None:
    """WAL + performance pragmas, applied to every new SQLite connection."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def make_sync_engine() -> "Engine":
    """Create a sync engine on :func:`sync_url` with the WAL pragmas attached."""
    from sqlalchemy import create_engine, event

    ensure_db_dir()
    engine = create_engine(
        sync_url(),
        pool_pre_ping=True,
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", set_sqlite_pragmas)
    return engine
