"""RAGKnowledgeBase against a real chromadb PersistentClient.

The rest of the RAG tests mock the collection. These run the real client and
chromadb's own SentenceTransformerEmbeddingFunction; only the model behind it
is faked, at the `sentence_transformers.SentenceTransformer` boundary, with a
deterministic hashed bag-of-words encoder. No network, no torch model load.
"""

from __future__ import annotations

import hashlib
import re
from unittest.mock import patch

import numpy as np
import pytest

pytest.importorskip("chromadb")
pytest.importorskip("sentence_transformers")

import services.rag_knowledge_base as rag_mod  # noqa: E402

try:
    from chromadb.api.shared_system_client import SharedSystemClient
except ImportError:  # chromadb 0.4
    from chromadb.api.client import SharedSystemClient

DIM = 64


class _BagOfWordsModel:
    """Stand-in for SentenceTransformer: texts sharing words embed close."""

    def __init__(self, *args, **kwargs):
        pass

    def encode(self, sentences, **kwargs):
        if isinstance(sentences, str):
            sentences = [sentences]
        out = np.zeros((len(sentences), DIM), dtype=np.float32)
        for i, s in enumerate(sentences):
            for tok in re.findall(r"\w+", s.lower()):
                out[i, int(hashlib.md5(tok.encode()).hexdigest(), 16) % DIM] += 1.0
        if kwargs.get("normalize_embeddings"):
            norms = np.linalg.norm(out, axis=1, keepdims=True)
            out = out / np.where(norms == 0, 1.0, norms)
        return out


def _clear_chroma_caches():
    # chromadb keeps one System per persist path; drop it between tests.
    SharedSystemClient.clear_system_cache()
    # chromadb's ST embedding function caches loaded models per class.
    models = getattr(
        rag_mod.embedding_functions.SentenceTransformerEmbeddingFunction, "models", None
    )
    if isinstance(models, dict):
        models.clear()


@pytest.fixture(autouse=True)
def _fake_model():
    if not rag_mod._RAG_AVAILABLE:
        pytest.skip("chromadb / sentence-transformers not importable")
    _clear_chroma_caches()
    with patch("sentence_transformers.SentenceTransformer", _BagOfWordsModel):
        yield
    _clear_chroma_caches()


def _kb(persist_dir) -> rag_mod.RAGKnowledgeBase:
    return rag_mod.RAGKnowledgeBase(collection_name="test_world", persist_dir=str(persist_dir))


DOCS = [
    "The dragon guards the ruined castle on the mountain.",
    "A quiet fishing village sits by the slow river.",
    "Merchants trade silk and spices in the capital market.",
]


class TestRealChroma:
    def test_add_and_query_returns_most_similar_chunk(self, tmp_path):
        kb = _kb(tmp_path / "chroma")
        assert kb.is_available

        added = kb.add_documents(DOCS, [{"source": "t", "chunk_index": i} for i in range(3)])

        assert added == 3
        assert kb.count() == 3
        assert kb.query("dragon castle mountain", n_results=1) == [DOCS[0]]
        # n_results larger than the collection is clamped, not an error
        assert len(kb.query("river", n_results=10)) == 3

    def test_index_chapter_and_query_structured(self, tmp_path):
        kb = _kb(tmp_path / "chroma")
        kb.index_chapter(1, "Linh enters the castle. The dragon wakes.", characters=["Linh"])
        kb.index_chapter(2, "Minh sails down the river to the village.", characters=["Minh"])

        hits = kb.query_structured("dragon castle", n_results=5)
        assert hits[0]["metadata"]["chapter_number"] == 1
        assert hits[0]["metadata"]["characters"] == "Linh"
        assert hits[0]["metadata"]["source"] == "generated"
        assert all(isinstance(h["distance"], float) for h in hits)

        only_two = kb.query_structured("dragon castle", n_results=5, where={"chapter_number": 2})
        assert [h["metadata"]["chapter_number"] for h in only_two] == [2]

        without_one = kb.query_structured("dragon castle", n_results=5, exclude_chapter=1)
        assert {h["metadata"]["chapter_number"] for h in without_one} == {2}

    def test_contains_filter_used_by_pipeline_runs_unfiltered(self, tmp_path):
        """context_helpers passes {"characters": {"$contains": name}}.

        chromadb 0.4 rejects `$contains` in a metadata filter, so the query is
        retried unfiltered. Pins that retrieval behaviour (chromadb 1.x would
        instead accept it and match nothing on these comma-joined strings).
        """
        kb = _kb(tmp_path / "chroma")
        kb.index_chapter(1, "Linh enters the castle.", characters=["Linh", "Minh"])
        kb.index_chapter(2, "Hoa waits by the river.", characters=["Hoa"])

        hits = kb.query_structured(
            "castle", n_results=5, where={"characters": {"$contains": "Linh"}}
        )

        assert [h["metadata"]["chapter_number"] for h in hits] == [1, 2]

    def test_data_survives_a_new_client(self, tmp_path):
        kb = _kb(tmp_path / "chroma")
        kb.add_documents(DOCS, [{"source": "t", "chunk_index": i} for i in range(3)])
        _clear_chroma_caches()

        reopened = _kb(tmp_path / "chroma")

        assert reopened.count() == 3
        assert reopened.query("silk spices market", n_results=1) == [DOCS[2]]

    def test_clear_empties_the_collection(self, tmp_path):
        kb = _kb(tmp_path / "chroma")
        kb.add_documents(DOCS, [{"source": "t", "chunk_index": i} for i in range(3)])

        kb.clear()

        assert kb.count() == 0
        assert kb.query("dragon") == []


class TestDegradation:
    def test_unreadable_store_disables_rag_and_is_left_alone(self, tmp_path):
        persist = tmp_path / "chroma"
        persist.mkdir()
        garbage = b"this is not a sqlite database" * 100
        (persist / "chroma.sqlite3").write_bytes(garbage)

        kb = _kb(persist)

        assert not kb.is_available
        assert kb.query("dragon") == []
        assert kb.add_documents(DOCS, [{"source": "t"}] * 3) == 0
        assert (persist / "chroma.sqlite3").read_bytes() == garbage

    def test_model_load_failure_disables_rag(self, tmp_path):
        with patch("sentence_transformers.SentenceTransformer", side_effect=OSError("offline")):
            kb = _kb(tmp_path / "chroma")

        assert not kb.is_available
        assert kb.query("dragon") == []
