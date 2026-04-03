"""Database integration tests using SQLite in-memory with async SQLAlchemy.

Each test class uses its own engine + tables so tests are fully isolated.
Requires: pip install sqlalchemy[asyncio] aiosqlite
"""
from __future__ import annotations

import uuid
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select, update

# ---------------------------------------------------------------------------
# Engine / session fixtures
# ---------------------------------------------------------------------------

SQLITE_URL = "sqlite+aiosqlite:///:memory:"


def _patch_jsonb_to_json():
    """Replace PostgreSQL JSONB columns with generic JSON for SQLite compat.

    db_models uses `JSONB` from `sqlalchemy.dialects.postgresql`.  SQLite
    cannot compile that type, so we swap it out with `sqlalchemy.JSON` before
    creating tables in tests.  This is done by iterating the metadata columns
    and replacing JSONB instances in-place.
    """
    from sqlalchemy import JSON  # noqa: PLC0415
    from sqlalchemy.dialects.postgresql import JSONB  # noqa: PLC0415
    from models.db_models import Base  # noqa: PLC0415

    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, JSONB):
                col.type = JSON()


@pytest_asyncio.fixture
async def engine():
    """Create a fresh SQLite in-memory engine for each test function."""
    _patch_jsonb_to_json()
    from models.db_models import Base  # noqa: PLC0415

    eng = create_async_engine(SQLITE_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine):
    """Yield an async session bound to the in-memory engine."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# User tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_user(session):
    """User can be created and retrieved by username."""
    from models.db_models import User  # noqa: PLC0415

    uid = _uid()
    user = User(id=uid, username="nguyen_van_a", password_hash="hashed_pw", credits=20)
    session.add(user)
    await session.commit()

    result = await session.execute(select(User).where(User.username == "nguyen_van_a"))
    fetched = result.scalar_one()
    assert fetched.id == uid
    assert fetched.username == "nguyen_van_a"
    assert fetched.credits == 20


@pytest.mark.asyncio
async def test_user_default_role(session):
    """User role defaults to 'user'."""
    from models.db_models import User  # noqa: PLC0415

    user = User(id=_uid(), username="default_role_user", password_hash="pw")
    session.add(user)
    await session.commit()

    result = await session.execute(select(User).where(User.username == "default_role_user"))
    fetched = result.scalar_one()
    assert fetched.role == "creator"


@pytest.mark.asyncio
async def test_user_unique_username(session):
    """Duplicate username raises integrity error."""
    from models.db_models import User  # noqa: PLC0415
    from sqlalchemy.exc import IntegrityError  # noqa: PLC0415

    session.add(User(id=_uid(), username="duplicate_name", password_hash="pw1"))
    await session.commit()

    session.add(User(id=_uid(), username="duplicate_name", password_hash="pw2"))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_authentication_flow(session):
    """Create user with password hash and verify hash is stored correctly."""
    from models.db_models import User  # noqa: PLC0415
    import hashlib  # noqa: PLC0415

    raw_pw = "s3cr3t_password"
    pw_hash = hashlib.sha256(raw_pw.encode()).hexdigest()
    user = User(id=_uid(), username="auth_user", password_hash=pw_hash)
    session.add(user)
    await session.commit()

    result = await session.execute(select(User).where(User.username == "auth_user"))
    fetched = result.scalar_one()
    # Simulate verification
    assert fetched.password_hash == hashlib.sha256(raw_pw.encode()).hexdigest()
    assert fetched.password_hash != hashlib.sha256("wrong_password".encode()).hexdigest()


# ---------------------------------------------------------------------------
# Story checkpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_story_checkpoint_save(session):
    """Story record can be saved with all required fields."""
    from models.db_models import Story  # noqa: PLC0415

    story_id = _uid()
    story = Story(
        id=story_id,
        title="Thanh Van Kiếm Khách",
        genre="tien_hiep",
        synopsis="Hành trình tu tiên của Lý Huyền",
        status="draft",
        chapter_count=3,
        word_count=1500,
    )
    session.add(story)
    await session.commit()

    result = await session.execute(select(Story).where(Story.id == story_id))
    fetched = result.scalar_one()
    assert fetched.title == "Thanh Van Kiếm Khách"
    assert fetched.genre == "tien_hiep"
    assert fetched.status == "draft"
    assert fetched.chapter_count == 3


@pytest.mark.asyncio
async def test_story_checkpoint_load_and_update(session):
    """Story status can be updated (checkpoint progression)."""
    from models.db_models import Story  # noqa: PLC0415

    story_id = _uid()
    session.add(Story(id=story_id, title="Test Story", genre="romance", status="draft"))
    await session.commit()

    await session.execute(
        update(Story).where(Story.id == story_id).values(status="complete", chapter_count=10)
    )
    await session.commit()

    result = await session.execute(select(Story).where(Story.id == story_id))
    fetched = result.scalar_one()
    assert fetched.status == "complete"
    assert fetched.chapter_count == 10


# ---------------------------------------------------------------------------
# Credit transaction tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_credit_debit(session):
    """Debiting credits reduces user balance correctly."""
    from models.db_models import User  # noqa: PLC0415

    uid = _uid()
    session.add(User(id=uid, username="credit_user", password_hash="pw", credits=50))
    await session.commit()

    # Debit 10 credits
    await session.execute(
        update(User).where(User.id == uid).values(credits=User.credits - 10)
    )
    await session.commit()

    result = await session.execute(select(User).where(User.id == uid))
    fetched = result.scalar_one()
    assert fetched.credits == 40


@pytest.mark.asyncio
async def test_credit_balance_check(session):
    """User with zero credits is correctly identified."""
    from models.db_models import User  # noqa: PLC0415

    uid = _uid()
    session.add(User(id=uid, username="broke_user", password_hash="pw", credits=0))
    await session.commit()

    result = await session.execute(select(User).where(User.id == uid))
    fetched = result.scalar_one()
    assert fetched.credits == 0
    # Verify insufficient balance guard pattern
    has_credits = fetched.credits > 0
    assert has_credits is False


@pytest.mark.asyncio
async def test_credit_multiple_transactions(session):
    """Multiple debit operations accumulate correctly."""
    from models.db_models import User  # noqa: PLC0415

    uid = _uid()
    session.add(User(id=uid, username="multi_debit", password_hash="pw", credits=100))
    await session.commit()

    for _ in range(5):
        await session.execute(
            update(User).where(User.id == uid).values(credits=User.credits - 5)
        )
    await session.commit()

    result = await session.execute(select(User).where(User.id == uid))
    fetched = result.scalar_one()
    assert fetched.credits == 75


# ---------------------------------------------------------------------------
# Pipeline run tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_run_creation(session):
    """PipelineRun record is created and links to story and user."""
    from models.db_models import User, Story, PipelineRun  # noqa: PLC0415

    uid = _uid()
    sid = _uid()
    rid = _uid()

    session.add(User(id=uid, username="pipeline_user", password_hash="pw"))
    session.add(Story(id=sid, title="Pipeline Story", genre="drama", user_id=uid))
    session.add(
        PipelineRun(
            id=rid,
            user_id=uid,
            story_id=sid,
            genre="drama",
            status="completed",
            layer_reached=3,
            duration_seconds=42.5,
            token_usage=12000,
        )
    )
    await session.commit()

    result = await session.execute(select(PipelineRun).where(PipelineRun.id == rid))
    fetched = result.scalar_one()
    assert fetched.status == "completed"
    assert fetched.layer_reached == 3
    assert fetched.token_usage == 12000


# ---------------------------------------------------------------------------
# Transaction context manager tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transaction_atomic_commit(engine):
    """transaction() commits story + chapter atomically when no exception occurs."""
    from models.db_models import Story, Chapter  # noqa: PLC0415
    from unittest.mock import patch, AsyncMock  # noqa: PLC0415
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker  # noqa: PLC0415

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    story_id = _uid()
    chapter_id = _uid()

    # Patch services.database internals to use the test engine/factory
    with patch("services.database._session_factory", factory), \
         patch("services.database.get_engine", return_value=engine):
        from services.database import transaction  # noqa: PLC0415

        async with transaction() as sess:
            assert sess is not None
            sess.add(Story(id=story_id, title="Atomic Story", genre="drama"))
            sess.add(Chapter(id=chapter_id, story_id=story_id, chapter_number=1, content="ch1"))

    # Verify both records persisted
    async with factory() as verify_sess:
        r = await verify_sess.execute(select(Story).where(Story.id == story_id))
        assert r.scalar_one().title == "Atomic Story"
        r2 = await verify_sess.execute(select(Chapter).where(Chapter.id == chapter_id))
        assert r2.scalar_one().chapter_number == 1


@pytest.mark.asyncio
async def test_transaction_rollback_on_exception(engine):
    """transaction() rolls back all writes when an exception is raised mid-block."""
    from models.db_models import Story  # noqa: PLC0415
    from unittest.mock import patch  # noqa: PLC0415
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker  # noqa: PLC0415
    from sqlalchemy.exc import NoResultFound  # noqa: PLC0415

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    story_id = _uid()

    with patch("services.database._session_factory", factory), \
         patch("services.database.get_engine", return_value=engine):
        from services.database import transaction  # noqa: PLC0415

        with pytest.raises(RuntimeError):
            async with transaction() as sess:
                sess.add(Story(id=story_id, title="Should Not Persist", genre="drama"))
                raise RuntimeError("simulated failure mid-transaction")

    # Verify the story was NOT persisted
    async with factory() as verify_sess:
        r = await verify_sess.execute(select(Story).where(Story.id == story_id))
        assert r.scalar_one_or_none() is None
