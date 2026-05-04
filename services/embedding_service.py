"""Local sentence-embedding service (Sprint 2, P1).

Lazy singleton wrapping `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
on CPU. Outputs L2-normalised float32 vectors so cosine similarity reduces to
a dot product.

Rationale: see `docs/adr/0002-semantic-verification.md`.

P1 scope: pure scaffolding. The cache (`services/embedding_cache.py`) lands in
P2; this module exposes a `_CacheBackend` Protocol and a no-op default so P2
can drop in the real SQLite-backed implementation without touching this file.

The pipeline modules (P3-P5) import via `get_embedding_service()`; do not
import this from L1/L2 modules until P3.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import unicodedata
from typing import TYPE_CHECKING, Protocol

import numpy as np

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Float32 little-endian — explicit so cache bytes are platform-stable.
_VEC_DTYPE = np.dtype("<f4")


# ---------------------------------------------------------------------------
# Cache backend protocol (real impl lands in P2)
# ---------------------------------------------------------------------------


class _CacheBackend(Protocol):
    """Stub interface that P2's `EmbeddingCache` will implement."""

    def get(self, key: str) -> bytes | None: ...

    def put(self, key: str, model_id: str, vec_bytes: bytes) -> None: ...


class _NullCache:
    """No-op cache used until P2 wires in the SQLite-backed implementation."""

    def get(self, key: str) -> bytes | None:  # noqa: D401 - protocol impl
        return None

    def put(self, key: str, model_id: str, vec_bytes: bytes) -> None:
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalise_text(text: str) -> str:
    """NFC-normalise + strip trailing whitespace.

    Vietnamese has multiple Unicode forms for the same character (precomposed
    vs combining diacritics). NFC ensures cache keys are stable regardless of
    upstream input form.
    """
    return unicodedata.normalize("NFC", text).strip()


def cache_key(model_id: str, text: str) -> str:
    """Deterministic cache key: sha256(model_id ␟ NFC(text))."""
    norm = _normalise_text(text)
    return hashlib.sha256(f"{model_id}␟{norm}".encode("utf-8")).hexdigest()


def vec_to_bytes(vec: np.ndarray) -> bytes:
    """Cast to little-endian float32 and return raw bytes (cache storage form)."""
    return np.ascontiguousarray(vec, dtype=_VEC_DTYPE).tobytes()


def bytes_to_vec(buf: bytes) -> np.ndarray:
    """Inverse of `vec_to_bytes`. Returns a 1-D float32 array."""
    return np.frombuffer(buf, dtype=_VEC_DTYPE)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class EmbeddingService:
    """Lazy singleton. CPU only. L2-normalised output.

    Use `get_embedding_service()` rather than constructing directly so the
    process-wide singleton (and its loaded model) is reused.
    """

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL,
        cache: _CacheBackend | None = None,
    ) -> None:
        self._model_id = model_id
        self._model: SentenceTransformer | None = None
        self._available: bool | None = None  # None = not probed yet
        self._lock = threading.Lock()
        self._cache: _CacheBackend = cache if cache is not None else _NullCache()

    # -- lifecycle ----------------------------------------------------------

    def _load(self) -> None:
        """Load the model on first use. Idempotent and thread-safe."""
        if self._model is not None or self._available is False:
            return
        with self._lock:
            if self._model is not None or self._available is False:
                return
            try:
                # Imported lazily so `import services.embedding_service` is
                # cheap (test-time imports must not pull torch).
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self._model_id, device="cpu")
                self._available = True
                logger.info("Embedding model loaded: %s", self._model_id)
            except Exception as exc:  # noqa: BLE001 - intentional broad catch
                logger.warning(
                    "Embedding model load failed (%s); degrading to keyword fallback.",
                    exc,
                )
                self._model = None
                self._available = False

    def is_available(self) -> bool:
        if self._available is None:
            self._load()
        return bool(self._available)

    @property
    def model_id(self) -> str:
        return self._model_id

    def attach_cache(self, cache: _CacheBackend) -> None:
        """P2 wiring hook — replaces the null cache with the real backend."""
        self._cache = cache

    # -- primary numpy API (called by P3-P5) --------------------------------

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        """Batched encode. Returns N×D float32 array, L2-normalised.

        Raises `RuntimeError` if the model failed to load. Callers in default
        mode should check `is_available()` first and degrade to the keyword
        fallback.
        """
        if not self.is_available():
            raise RuntimeError("Embedding service unavailable")
        assert self._model is not None  # for type-checkers; guaranteed by is_available
        result = self._model.encode(
            texts,
            batch_size=32,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return np.ascontiguousarray(result, dtype=_VEC_DTYPE)

    @staticmethod
    def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity. Inputs assumed L2-normalised."""
        return float(np.dot(a, b))

    # -- bytes API (cache-friendly thin wrappers) ---------------------------

    def embed(self, text: str) -> bytes:
        """Single-text embed returning raw float32 LE bytes (cache form).

        Reads through the attached cache when present.
        """
        key = cache_key(self._model_id, text)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        vec = self.embed_texts([text])[0]
        buf = vec_to_bytes(vec)
        self._cache.put(key, self._model_id, buf)
        return buf

    def embed_batch(self, texts: list[str]) -> list[bytes]:
        """Batch embed returning a list of raw float32 LE byte strings.

        Cache lookup per text; only misses are sent to the underlying model.
        """
        out: list[bytes | None] = [None] * len(texts)
        miss_indices: list[int] = []
        miss_texts: list[str] = []

        for i, t in enumerate(texts):
            key = cache_key(self._model_id, t)
            cached = self._cache.get(key)
            if cached is not None:
                out[i] = cached
            else:
                miss_indices.append(i)
                miss_texts.append(t)

        if miss_texts:
            vecs = self.embed_texts(miss_texts)
            for idx, t, vec in zip(miss_indices, miss_texts, vecs, strict=True):
                buf = vec_to_bytes(vec)
                self._cache.put(cache_key(self._model_id, t), self._model_id, buf)
                out[idx] = buf

        # mypy: all slots populated by construction
        return [b for b in out if b is not None]

    @staticmethod
    def similarity(vec_a: bytes, vec_b: bytes) -> float:
        """Cosine similarity over the bytes form. Assumes L2-normalised inputs."""
        a = bytes_to_vec(vec_a)
        b = bytes_to_vec(vec_b)
        return float(np.dot(a, b))


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------


_service: EmbeddingService | None = None
_singleton_lock = threading.Lock()


def get_embedding_service(model_id: str | None = None) -> EmbeddingService:
    """Process-wide singleton accessor.

    Switching `model_id` (e.g. via config reload) yields a fresh instance —
    cache keys include the model_id so this is safe.
    """
    global _service
    with _singleton_lock:
        if _service is None or (model_id and _service.model_id != model_id):
            _service = EmbeddingService(model_id or DEFAULT_MODEL)
        return _service


def reset_embedding_service() -> None:
    """Test helper. Drops the singleton so the next call reloads."""
    global _service
    with _singleton_lock:
        _service = None


__all__ = [
    "DEFAULT_MODEL",
    "EmbeddingService",
    "cache_key",
    "vec_to_bytes",
    "bytes_to_vec",
    "get_embedding_service",
    "reset_embedding_service",
]
