"""Unit tests for `services/embedding_service.py` (Sprint 2, P1).

Mocks `SentenceTransformer` — must not download or load the real model.
"""

from __future__ import annotations

import sys
import types
import unicodedata
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Inject a stub `sentence_transformers` module so `patch(...)` can resolve the
# attribute even on hosts without the heavy ML dependency installed. The real
# package is exercised by P7's integration test, not by these unit tests.
if "sentence_transformers" not in sys.modules:
    _stub = types.ModuleType("sentence_transformers")
    _stub.SentenceTransformer = MagicMock(name="SentenceTransformer")  # type: ignore[attr-defined]
    sys.modules["sentence_transformers"] = _stub

from services import embedding_service as es  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    """Drop the singleton between tests so each test starts clean."""
    es.reset_embedding_service()
    yield
    es.reset_embedding_service()


def _fake_model_returning(vectors: np.ndarray) -> MagicMock:
    """Build a fake SentenceTransformer that returns the given vectors."""
    model = MagicMock()
    model.encode = MagicMock(return_value=vectors)
    return model


# ---------------------------------------------------------------------------
# Cache key + normalisation
# ---------------------------------------------------------------------------


class TestCacheKey:
    def test_deterministic_same_input_same_key(self) -> None:
        a = es.cache_key("model-x", "hello world")
        b = es.cache_key("model-x", "hello world")
        assert a == b
        assert len(a) == 64  # sha256 hex

    def test_different_model_yields_different_key(self) -> None:
        a = es.cache_key("model-x", "hello")
        b = es.cache_key("model-y", "hello")
        assert a != b

    def test_different_text_yields_different_key(self) -> None:
        a = es.cache_key("model-x", "hello")
        b = es.cache_key("model-x", "goodbye")
        assert a != b

    def test_nfc_normalisation_handles_vietnamese_decomposed_form(self) -> None:
        """Combining vs precomposed Vietnamese diacritics must hash the same."""
        # "ế" precomposed (U+1EBF) vs decomposed (e + combining ^ + combining ́)
        precomposed = "kiếm"
        decomposed = unicodedata.normalize("NFD", precomposed)
        assert precomposed != decomposed  # sanity: forms differ as bytes
        assert es.cache_key("m", precomposed) == es.cache_key("m", decomposed)

    def test_trailing_whitespace_stripped(self) -> None:
        assert es.cache_key("m", "hello") == es.cache_key("m", "hello   ")
        assert es.cache_key("m", "hello") == es.cache_key("m", "hello\n")


class TestVecBytesRoundtrip:
    def test_roundtrip_preserves_values(self) -> None:
        vec = np.array([1.0, -0.5, 0.25, 0.0], dtype=np.float32)
        buf = es.vec_to_bytes(vec)
        out = es.bytes_to_vec(buf)
        np.testing.assert_array_equal(out, vec)

    def test_bytes_form_is_float32_le(self) -> None:
        vec = np.array([1.0, 0.0], dtype=np.float32)
        buf = es.vec_to_bytes(vec)
        # 2 floats × 4 bytes = 8 bytes
        assert len(buf) == 8

    def test_accepts_float64_input(self) -> None:
        vec = np.array([1.0, 0.5], dtype=np.float64)
        buf = es.vec_to_bytes(vec)
        out = es.bytes_to_vec(buf)
        np.testing.assert_allclose(out, vec, rtol=1e-6)


# ---------------------------------------------------------------------------
# EmbeddingService — model loading
# ---------------------------------------------------------------------------


class TestModelLoading:
    def test_lazy_load_not_called_on_init(self) -> None:
        """Constructing the service must not import or load the model."""
        with patch("sentence_transformers.SentenceTransformer") as mock_st:
            svc = es.EmbeddingService("any-model")
            mock_st.assert_not_called()
            # Internal state — not yet probed.
            assert svc._available is None
            assert svc._model is None

    def test_is_available_triggers_load(self) -> None:
        fake = _fake_model_returning(np.zeros((1, 4), dtype=np.float32))
        with patch(
            "sentence_transformers.SentenceTransformer", return_value=fake
        ) as mock_st:
            svc = es.EmbeddingService("m")
            assert svc.is_available() is True
            mock_st.assert_called_once_with("m", device="cpu")

    def test_load_failure_marks_unavailable(self) -> None:
        with patch(
            "sentence_transformers.SentenceTransformer",
            side_effect=RuntimeError("boom"),
        ):
            svc = es.EmbeddingService("m")
            assert svc.is_available() is False
            # Calling again must not retry endlessly.
            assert svc.is_available() is False

    def test_load_idempotent(self) -> None:
        fake = _fake_model_returning(np.zeros((1, 4), dtype=np.float32))
        with patch(
            "sentence_transformers.SentenceTransformer", return_value=fake
        ) as mock_st:
            svc = es.EmbeddingService("m")
            svc.is_available()
            svc.is_available()
            svc.is_available()
            mock_st.assert_called_once()


# ---------------------------------------------------------------------------
# EmbeddingService — embed_texts (numpy API)
# ---------------------------------------------------------------------------


class TestEmbedTexts:
    def test_returns_numpy_array(self) -> None:
        vecs = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
        fake = _fake_model_returning(vecs)
        with patch("sentence_transformers.SentenceTransformer", return_value=fake):
            svc = es.EmbeddingService("m")
            out = svc.embed_texts(["a", "b"])
        np.testing.assert_array_equal(out, vecs)
        assert out.dtype == np.float32

    def test_calls_encode_with_normalize(self) -> None:
        fake = _fake_model_returning(np.zeros((1, 4), dtype=np.float32))
        with patch("sentence_transformers.SentenceTransformer", return_value=fake):
            svc = es.EmbeddingService("m")
            svc.embed_texts(["x"])
        kwargs = fake.encode.call_args.kwargs
        assert kwargs["normalize_embeddings"] is True
        assert kwargs["convert_to_numpy"] is True
        assert kwargs["show_progress_bar"] is False

    def test_raises_when_unavailable(self) -> None:
        with patch(
            "sentence_transformers.SentenceTransformer",
            side_effect=RuntimeError("boom"),
        ):
            svc = es.EmbeddingService("m")
            with pytest.raises(RuntimeError, match="unavailable"):
                svc.embed_texts(["x"])


class TestCosineSim:
    def test_identical_normalised_vecs_score_1(self) -> None:
        a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        sim = es.EmbeddingService.cosine_sim(a, a)
        assert sim == pytest.approx(1.0)

    def test_orthogonal_vecs_score_0(self) -> None:
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([0.0, 1.0], dtype=np.float32)
        assert es.EmbeddingService.cosine_sim(a, b) == pytest.approx(0.0)

    def test_opposite_vecs_score_negative(self) -> None:
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([-1.0, 0.0], dtype=np.float32)
        assert es.EmbeddingService.cosine_sim(a, b) == pytest.approx(-1.0)


# ---------------------------------------------------------------------------
# EmbeddingService — bytes API + cache integration
# ---------------------------------------------------------------------------


class _DictCache:
    """In-memory cache backend for tests."""

    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}
        self.put_calls = 0

    def get(self, key: str) -> bytes | None:
        return self.store.get(key)

    def put(self, key: str, model_id: str, vec_bytes: bytes) -> None:
        self.put_calls += 1
        self.store[key] = vec_bytes


class TestEmbedBytesAPI:
    def test_embed_returns_bytes_and_writes_cache(self) -> None:
        vec = np.array([0.6, 0.8], dtype=np.float32)
        fake = _fake_model_returning(np.array([[0.6, 0.8]], dtype=np.float32))
        cache = _DictCache()
        with patch("sentence_transformers.SentenceTransformer", return_value=fake):
            svc = es.EmbeddingService("m", cache=cache)
            buf = svc.embed("hello")
        assert es.bytes_to_vec(buf).tolist() == pytest.approx(vec.tolist())
        assert len(cache.store) == 1
        assert cache.put_calls == 1

    def test_embed_hits_cache_on_second_call(self) -> None:
        fake = _fake_model_returning(np.array([[1.0, 0.0]], dtype=np.float32))
        cache = _DictCache()
        with patch("sentence_transformers.SentenceTransformer", return_value=fake):
            svc = es.EmbeddingService("m", cache=cache)
            svc.embed("hello")
            svc.embed("hello")  # cache hit — must not re-encode
        # encode invoked exactly once across the two embed() calls
        assert fake.encode.call_count == 1

    def test_embed_batch_mixed_hit_miss(self) -> None:
        # Two-text batch: first call populates cache for "a" only; second
        # batch with ["a", "b"] should encode just "b".
        vecs_a = np.array([[1.0, 0.0]], dtype=np.float32)
        vecs_b = np.array([[0.0, 1.0]], dtype=np.float32)
        fake = MagicMock()
        fake.encode = MagicMock(side_effect=[vecs_a, vecs_b])
        cache = _DictCache()
        with patch("sentence_transformers.SentenceTransformer", return_value=fake):
            svc = es.EmbeddingService("m", cache=cache)
            svc.embed("a")  # encode #1
            results = svc.embed_batch(["a", "b"])  # encode #2 for "b" only
        assert fake.encode.call_count == 2
        assert len(results) == 2
        # Result for "a" matches cached bytes exactly.
        assert results[0] == es.vec_to_bytes(vecs_a[0])
        assert results[1] == es.vec_to_bytes(vecs_b[0])

    def test_embed_batch_all_cached_skips_model(self) -> None:
        fake = _fake_model_returning(np.array([[1.0, 0.0]], dtype=np.float32))
        cache = _DictCache()
        with patch("sentence_transformers.SentenceTransformer", return_value=fake):
            svc = es.EmbeddingService("m", cache=cache)
            svc.embed("x")
            fake.encode.reset_mock()
            results = svc.embed_batch(["x", "x", "x"])
        fake.encode.assert_not_called()
        assert len(results) == 3

    def test_attach_cache_replaces_null_cache(self) -> None:
        fake = _fake_model_returning(np.array([[1.0, 0.0]], dtype=np.float32))
        cache = _DictCache()
        with patch("sentence_transformers.SentenceTransformer", return_value=fake):
            svc = es.EmbeddingService("m")
            svc.attach_cache(cache)
            svc.embed("y")
        assert len(cache.store) == 1


class TestSimilarity:
    def test_bytes_form_cosine(self) -> None:
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([0.0, 1.0], dtype=np.float32)
        sim = es.EmbeddingService.similarity(es.vec_to_bytes(a), es.vec_to_bytes(b))
        assert sim == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_returns_same_instance(self) -> None:
        a = es.get_embedding_service()
        b = es.get_embedding_service()
        assert a is b

    def test_changing_model_id_yields_new_instance(self) -> None:
        a = es.get_embedding_service("model-1")
        b = es.get_embedding_service("model-2")
        assert a is not b
        assert b.model_id == "model-2"

    def test_default_model_id(self) -> None:
        svc = es.get_embedding_service()
        assert svc.model_id == es.DEFAULT_MODEL

    def test_reset_drops_singleton(self) -> None:
        a = es.get_embedding_service()
        es.reset_embedding_service()
        b = es.get_embedding_service()
        assert a is not b
