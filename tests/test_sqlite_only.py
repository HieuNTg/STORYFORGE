"""SQLite is the only data store: no Redis, Postgres or Alembic.

Pins the Task 5 contract: one SQLite file located by ``STORYFORGE_DB_PATH``
(default ``data/storyforge.db``), tables created on every start, and no module
reading ``REDIS_URL``/``DATABASE_URL`` or importing redis/asyncpg/alembic.
"""

import subprocess
from pathlib import Path

import sqlalchemy
from sqlalchemy import create_engine

from services.infra.database import init_db
from services.infra.db_paths import async_url, db_path, sync_url

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_db_path_honours_env(tmp_path, monkeypatch):
    monkeypatch.setenv("STORYFORGE_DB_PATH", str(tmp_path / "x.db"))
    assert sync_url() == f"sqlite:///{tmp_path / 'x.db'}"
    assert async_url().startswith("sqlite+aiosqlite:///")


def test_db_path_defaults_to_repo_data_dir(monkeypatch):
    monkeypatch.delenv("STORYFORGE_DB_PATH", raising=False)
    assert db_path() == _REPO_ROOT / "data" / "storyforge.db"


async def test_init_db_creates_tables_without_database_url(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("STORYFORGE_DB_PATH", str(tmp_path / "s.db"))
    assert await init_db() is True
    names = set(sqlalchemy.inspect(create_engine(sync_url())).get_table_names())
    assert {"stories", "chapters", "pipeline_runs"} <= names
    assert "users" not in names


async def test_session_round_trips_on_sqlite_file(tmp_path, monkeypatch):
    from models.db_models import Story
    from services.infra.database import close_db, get_engine, get_session

    monkeypatch.setenv("STORYFORGE_DB_PATH", str(tmp_path / "nested" / "r.db"))
    assert get_engine() is not None
    assert await init_db() is True
    async with get_session() as session:
        session.add(Story(id="s-1", title="Truyện"))
    async with get_session() as session:
        assert (await session.get(Story, "s-1")).title == "Truyện"
    await close_db()
    assert (tmp_path / "nested" / "r.db").exists()


def test_no_module_reads_redis_or_database_url():
    hits = subprocess.run(
        [
            "git",
            "grep",
            "-nE",
            "REDIS_URL|DATABASE_URL|import redis|asyncpg|alembic",
            "--",
            "*.py",
            ":!tests",
        ],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    ).stdout
    assert hits == ""


def test_health_reports_sqlite_ok(client):
    body = client.get("/api/health").json()
    assert body["services"]["database"] == "ok" and "redis" not in body["services"]
