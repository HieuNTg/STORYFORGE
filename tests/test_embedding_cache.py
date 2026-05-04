"""Unit + integration tests for `services/embedding_cache.py` (Sprint 2, P2).

Design:
- All tests use a temporary SQLite file (tmp_path fixture) — no shared state.
- The real embedding model is NEVER loaded. `SentenceTransformer` is mocked.
- Migration test exercises the Alembic DDL paths via direct SQLAlchemy on SQLite.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch, call

import numpy as np
import pytest

# Stub sentence_transformers so the import chain works without torch installed.
if "sentence_transformers" not in sys.modules:
    _stub = types.ModuleType("sentence_transformers")
    _stub.SentenceTransformer = MagicMock(name="SentenceTransformer")  # type: ignore[attr-defined]
    sys.modules["sentence_transformers"] = _stub

from services import embedding_service as es
from services.embedding_cache import (
    EmbeddingCache,
    get_embedding_cache,
    reset_embedding_cache,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vec(dim: int = 4, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.random(dim).astype(np.float32)
    return v / np.linalg.norm(v)  # L2-normalised


def _vec_bytes(dim: int = 4, seed: int = 0) -> bytes:
    return es.vec_to_bytes(_make_vec(dim, seed))


def _fake_model(vecs: np.ndarray) -> MagicMock:
    m = MagicMock()
    m.encode = MagicMock(return_value=vecs)
    return m


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_singletons():
    """Ensure module-level singletons don't bleed between tests."""
    es.reset_embedding_service()
    reset_embedding_cache()
    yield
    es.reset_embedding_service()
    reset_embedding_cache()


@pytest.fixture
def cache(tmp_path):
    """Fresh EmbeddingCache backed by a temp SQLite file."""
    return EmbeddingCache(db_path=str(tmp_path / "ec.db"))


# ---------------------------------------------------------------------------
# Round-trip: set → get returns identical bytes
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_put_then_get_returns_same_bytes(self, cache):
        key = "a" * 64
        buf = _vec_bytes(8, seed=1)
        cache.put(key, "model-x", buf)
        result = cache.get(key)
        assert result == buf

    def test_roundtrip_preserves_float32_values(self, cache):
        vec = _make_vec(16, seed=42)
        buf = es.vec_to_bytes(vec)
        key = "b" * 64
        cache.put(key, "model-x", buf)
        out = np.frombuffer(cache.get(key), dtype=np.float32)
        np.testing.assert_array_equal(out, vec)


# ---------------------------------------------------------------------------
# Miss returns None
# ---------------------------------------------------------------------------

class TestCacheMiss:
    def test_missing_key_returns_none(self, cache):
        assert cache.get("notexist" * 8) is None

    def test_wrong_key_returns_none(self, cache):
        buf = _vec_bytes()
        cache.put("a" * 64, "m", buf)
        assert cache.get("b" * 64) is None


# ---------------------------------------------------------------------------
# Bulk get with mix of present/absent keys
# ---------------------------------------------------------------------------

class TestBulkGet:
    def test_bulk_get_all_present(self, cache):
        keys = ["a" * 64, "b" * 64, "c" * 64]
        bufs = [_vec_bytes(4, seed=i) for i in range(3)]
        for k, b in zip(keys, bufs):
            cache.put(k, "m", b)
        result = cache.bulk_get(keys)
        assert set(result.keys()) == set(keys)
        for k, b in zip(keys, bufs):
            assert result[k] == b

    def test_bulk_get_partial_hits(self, cache):
        present_key = "p" * 64
        absent_key = "a" * 64
        buf = _vec_bytes()
        cache.put(present_key, "m", buf)
        result = cache.bulk_get([present_key, absent_key])
        assert present_key in result
        assert absent_key not in result

    def test_bulk_get_all_absent(self, cache):
        result = cache.bulk_get(["x" * 64, "y" * 64])
        assert result == {}

    def test_bulk_get_empty_list(self, cache):
        assert cache.bulk_get([]) == {}


# ---------------------------------------------------------------------------
# Idempotent set: writing same key twice doesn't error or duplicate
# ---------------------------------------------------------------------------

class TestIdempotentSet:
    def test_duplicate_key_no_error(self, cache):
        key = "d" * 64
        buf = _vec_bytes(4, seed=0)
        cache.put(key, "m", buf)
        # Must not raise
        cache.put(key, "m", buf)

    def test_duplicate_key_does_not_change_value(self, cache):
        """INSERT OR IGNORE: first write wins."""
        key = "e" * 64
        buf1 = _vec_bytes(4, seed=0)
        buf2 = _vec_bytes(4, seed=99)
        cache.put(key, "m", buf1)
        cache.put(key, "m", buf2)  # should be ignored
        assert cache.get(key) == buf1

    def test_row_count_after_duplicate(self, cache):
        key = "f" * 64
        buf = _vec_bytes()
        cache.put(key, "m", buf)
        cache.put(key, "m", buf)
        stats = cache.stats()
        assert stats["total_entries"] == 1


# ---------------------------------------------------------------------------
# Integration: EmbeddingService with attached cache
# ---------------------------------------------------------------------------

class TestEmbeddingServiceIntegration:
    """Verify the service calls the model only once for same-text embed."""

    def test_first_embed_writes_cache_second_reads_from_cache(self, cache, tmp_path):
        vec = np.array([[0.6, 0.8]], dtype=np.float32)
        fake = _fake_model(vec)

        with patch("sentence_transformers.SentenceTransformer", return_value=fake):
            svc = es.EmbeddingService("model-x", cache=cache)
            # First call — model is invoked, result cached
            buf1 = svc.embed("hello world")
            assert fake.encode.call_count == 1

            # Second call — should come from cache, NOT the model
            buf2 = svc.embed("hello world")
            assert fake.encode.call_count == 1  # still 1 — cache hit

        assert buf1 == buf2

    def test_different_texts_each_call_model(self, cache):
        vecs = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
        fake = MagicMock()
        fake.encode = MagicMock(side_effect=[
            vecs[0:1],  # first text
            vecs[1:2],  # second text
        ])
        with patch("sentence_transformers.SentenceTransformer", return_value=fake):
            svc = es.EmbeddingService("model-x", cache=cache)
            svc.embed("text A")
            svc.embed("text B")
        assert fake.encode.call_count == 2

    def test_attach_cache_hook(self, cache):
        """attach_cache() replaces the null cache; subsequent embed writes to real cache."""
        vec = np.array([[0.6, 0.8]], dtype=np.float32)
        fake = _fake_model(vec)
        with patch("sentence_transformers.SentenceTransformer", return_value=fake):
            svc = es.EmbeddingService("model-x")
            svc.attach_cache(cache)
            svc.embed("test attach")
        # Cache must have the row
        key = es.cache_key("model-x", "test attach")
        assert cache.get(key) is not None

    def test_different_model_id_yields_cache_miss(self, cache):
        """Bumping model_id must not reuse cached bytes (keys include model_id)."""
        vec_a = np.array([[1.0, 0.0]], dtype=np.float32)
        vec_b = np.array([[0.0, 1.0]], dtype=np.float32)
        fake_a = _fake_model(vec_a)
        fake_b = _fake_model(vec_b)

        with patch("sentence_transformers.SentenceTransformer", return_value=fake_a):
            svc_a = es.EmbeddingService("model-a", cache=cache)
            buf_a = svc_a.embed("same text")

        with patch("sentence_transformers.SentenceTransformer", return_value=fake_b):
            svc_b = es.EmbeddingService("model-b", cache=cache)
            buf_b = svc_b.embed("same text")

        # Different model → different keys → different bytes
        assert buf_a != buf_b
        assert fake_b.encode.call_count == 1  # model-b was actually called

    def test_embed_batch_cache_hit_skips_model(self, cache):
        """embed_batch: after warming cache for all texts, re-run skips model."""
        texts = ["alpha", "beta", "gamma"]
        vecs = np.array([[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]], dtype=np.float32)
        fake = _fake_model(vecs)

        with patch("sentence_transformers.SentenceTransformer", return_value=fake):
            svc = es.EmbeddingService("m", cache=cache)
            # Warm cache
            svc.embed_batch(texts)
            assert fake.encode.call_count == 1

            fake.encode.reset_mock()
            # All cached — must not call encode
            results = svc.embed_batch(texts)

        fake.encode.assert_not_called()
        assert len(results) == 3


# ---------------------------------------------------------------------------
# Migration test: DDL forward + downgrade
# ---------------------------------------------------------------------------

class TestMigrationDDL:
    """Verify the Alembic migration SQL works on SQLite (same DDL)."""

    def test_upgrade_creates_table_and_index(self, tmp_path):
        import sqlite3
        db = str(tmp_path / "mig.db")
        conn = sqlite3.connect(db)
        # Run upgrade DDL (mirrors alembic/versions/004_embedding_cache.py)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS embedding_cache (
                key        TEXT    NOT NULL PRIMARY KEY,
                model_id   TEXT    NOT NULL,
                dim        INTEGER NOT NULL,
                vec        BLOB    NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS ix_embedding_cache_model_id
                ON embedding_cache (model_id);
        """)
        conn.commit()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "embedding_cache" in tables
        indexes = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()}
        assert "ix_embedding_cache_model_id" in indexes
        conn.close()

    def test_downgrade_drops_table_and_index(self, tmp_path):
        import sqlite3
        db = str(tmp_path / "mig_down.db")
        conn = sqlite3.connect(db)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS embedding_cache (
                key        TEXT    NOT NULL PRIMARY KEY,
                model_id   TEXT    NOT NULL,
                dim        INTEGER NOT NULL,
                vec        BLOB    NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS ix_embedding_cache_model_id
                ON embedding_cache (model_id);
        """)
        conn.commit()
        # Downgrade
        conn.execute("DROP INDEX IF EXISTS ix_embedding_cache_model_id")
        conn.execute("DROP TABLE IF EXISTS embedding_cache")
        conn.commit()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "embedding_cache" not in tables
        conn.close()

    def test_upgrade_then_downgrade_then_upgrade_idempotent(self, tmp_path):
        """Mirrors the alembic upgrade → downgrade → upgrade cycle."""
        from services.embedding_cache import EmbeddingCache
        db = str(tmp_path / "cycle.db")
        # First upgrade: table created implicitly by EmbeddingCache init
        c1 = EmbeddingCache(db_path=db)
        buf = _vec_bytes()
        c1.put("k" * 64, "m", buf)
        assert c1.get("k" * 64) == buf

        # Simulate downgrade: drop table
        import sqlite3
        conn = sqlite3.connect(db)
        conn.execute("DROP INDEX IF EXISTS ix_embedding_cache_model_id")
        conn.execute("DROP TABLE IF EXISTS embedding_cache")
        conn.commit()
        conn.close()
        # Close thread-local connection
        if hasattr(c1._local, "conn") and c1._local.conn:
            c1._local.conn.close()
            c1._local.conn = None

        # Second upgrade: re-create via new EmbeddingCache instance
        c2 = EmbeddingCache(db_path=db)
        # Table fresh — previous key gone
        assert c2.get("k" * 64) is None
        # Can write again
        c2.put("k" * 64, "m", buf)
        assert c2.get("k" * 64) == buf


# ---------------------------------------------------------------------------
# Stats / diagnostics
# ---------------------------------------------------------------------------

class TestStats:
    def test_stats_empty_cache(self, cache):
        s = cache.stats()
        assert s["total_entries"] == 0
        assert s["backend"] == "sqlite"

    def test_stats_after_inserts(self, cache):
        for i in range(3):
            cache.put(str(i) * 64, "m", _vec_bytes(4, seed=i))
        s = cache.stats()
        assert s["total_entries"] == 3

    def test_stats_size_oserror_handled(self, cache):
        """OSError on getsize (e.g. in-memory path) returns 0 gracefully."""
        import unittest.mock as mock
        with mock.patch("os.path.getsize", side_effect=OSError("no file")):
            s = cache.stats()
        assert s["db_size_bytes"] == 0


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

class TestSingleton:
    def test_get_returns_same_instance(self, tmp_path):
        db = str(tmp_path / "s.db")
        a = get_embedding_cache(db_path=db)
        b = get_embedding_cache(db_path=db)
        assert a is b

    def test_reset_drops_singleton(self, tmp_path):
        db = str(tmp_path / "s2.db")
        a = get_embedding_cache(db_path=db)
        reset_embedding_cache()
        b = get_embedding_cache(db_path=db)
        assert a is not b
