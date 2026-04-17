"""Sprint 2 Task 1 — index_chapter + query_structured unit tests.

Uses a fake collection to avoid requiring chromadb at test-time. The tests
exercise metadata shaping and the structured-query post-filter logic.
"""
from __future__ import annotations

from typing import Any

import pytest

from services.rag_knowledge_base import RAGKnowledgeBase


class _FakeCollection:
    def __init__(self):
        self.docs: list[str] = []
        self.metadatas: list[dict] = []
        self.ids: list[str] = []
        self.last_query_kwargs: dict[str, Any] | None = None
        self.next_query_result: dict | None = None
        self.raise_on_where: bool = False

    def add(self, documents, metadatas, ids):
        self.docs.extend(documents)
        self.metadatas.extend(metadatas)
        self.ids.extend(ids)

    def count(self):
        return len(self.docs)

    def query(self, **kwargs):
        self.last_query_kwargs = kwargs
        if self.raise_on_where and "where" in kwargs:
            raise RuntimeError("simulated chroma where syntax error")
        if self.next_query_result is not None:
            return self.next_query_result
        # Default: return everything up to n_results in insertion order
        n = kwargs.get("n_results", len(self.docs))
        docs = self.docs[:n]
        metas = self.metadatas[:n]
        dists = [0.1 * i for i in range(len(docs))]
        return {
            "documents": [docs],
            "metadatas": [metas],
            "distances": [dists],
        }


@pytest.fixture
def kb_with_fake():
    """Bypass real chromadb; attach a fake collection."""
    kb = RAGKnowledgeBase.__new__(RAGKnowledgeBase)
    kb._available = True
    kb._collection_name = "test"
    kb._persist_dir = ""
    kb._client = None
    kb._ef = None
    kb._collection = _FakeCollection()
    return kb


class TestIndexChapter:
    def test_empty_content_returns_zero(self, kb_with_fake):
        assert kb_with_fake.index_chapter(1, "") == 0
        assert kb_with_fake.index_chapter(1, "   \n  ") == 0

    def test_chunks_and_metadata_shape(self, kb_with_fake):
        content = "First sentence. Second sentence! Third line? " * 40
        added = kb_with_fake.index_chapter(
            chapter_number=5,
            content=content,
            characters=["Linh", "An"],
            threads=["love_triangle"],
            summary="summary " * 50,  # will be capped
        )
        assert added > 0
        coll = kb_with_fake._collection
        assert len(coll.docs) == added
        meta = coll.metadatas[0]
        assert meta["source"] == "generated"
        assert meta["chapter_number"] == 5
        assert meta["chunk_index"] == 0
        assert meta["characters"] == "Linh,An"
        assert meta["threads"] == "love_triangle"
        assert len(meta["summary"]) <= 200

    def test_indices_increment(self, kb_with_fake):
        content = "Sentence one. " * 300  # force many chunks
        kb_with_fake.index_chapter(2, content)
        coll = kb_with_fake._collection
        assert coll.metadatas[0]["chunk_index"] == 0
        assert coll.metadatas[-1]["chunk_index"] == len(coll.docs) - 1

    def test_defaults_when_no_chars_or_threads(self, kb_with_fake):
        kb_with_fake.index_chapter(1, "Một câu. Hai câu.")
        meta = kb_with_fake._collection.metadatas[0]
        assert meta["characters"] == ""
        assert meta["threads"] == ""
        assert meta["summary"] == ""

    def test_unavailable_kb_is_noop(self):
        kb = RAGKnowledgeBase.__new__(RAGKnowledgeBase)
        kb._available = False
        kb._collection = None
        assert kb.index_chapter(1, "content here.") == 0


class TestQueryStructured:
    def test_empty_question_returns_empty(self, kb_with_fake):
        assert kb_with_fake.query_structured("") == []
        assert kb_with_fake.query_structured("   ") == []

    def test_empty_collection_returns_empty(self, kb_with_fake):
        assert kb_with_fake.query_structured("anything") == []

    def test_returns_structured_items(self, kb_with_fake):
        kb_with_fake.index_chapter(1, "Câu một. Câu hai.", characters=["A"])
        kb_with_fake.index_chapter(2, "Câu ba. Câu bốn.", characters=["B"])
        results = kb_with_fake.query_structured("câu", n_results=5)
        assert results
        first = results[0]
        assert "text" in first and "metadata" in first and "distance" in first
        assert first["metadata"]["chapter_number"] in (1, 2)

    def test_exclude_chapter(self, kb_with_fake):
        kb_with_fake.index_chapter(1, "Câu A. Câu B.")
        kb_with_fake.index_chapter(2, "Câu C. Câu D.")
        results = kb_with_fake.query_structured("câu", n_results=10, exclude_chapter=1)
        assert all(r["metadata"]["chapter_number"] != 1 for r in results)

    def test_where_filter_passed_through(self, kb_with_fake):
        kb_with_fake.index_chapter(1, "Câu A.")
        kb_with_fake.query_structured(
            "câu", n_results=3, where={"characters": {"$contains": "Linh"}},
        )
        assert kb_with_fake._collection.last_query_kwargs["where"] == {
            "characters": {"$contains": "Linh"}
        }

    def test_where_filter_fallback_on_error(self, kb_with_fake):
        kb_with_fake.index_chapter(1, "Câu A.")
        kb_with_fake._collection.raise_on_where = True
        results = kb_with_fake.query_structured(
            "câu", n_results=3, where={"characters": {"$contains": "Linh"}},
        )
        # Should still return items via fallback (no where)
        assert results

    def test_handles_missing_distances_key(self, kb_with_fake):
        # Pre-seed
        kb_with_fake.index_chapter(1, "Câu A. Câu B.")
        kb_with_fake._collection.next_query_result = {
            "documents": [["Câu A."]],
            "metadatas": [[{"chapter_number": 1, "chunk_index": 0}]],
            # distances missing
        }
        results = kb_with_fake.query_structured("câu", n_results=1)
        assert len(results) == 1
        assert results[0]["distance"] == 0.0

    def test_skips_empty_docs(self, kb_with_fake):
        kb_with_fake.index_chapter(1, "Câu A.")
        kb_with_fake._collection.next_query_result = {
            "documents": [["", "Câu A."]],
            "metadatas": [[{"chapter_number": 1}, {"chapter_number": 1}]],
            "distances": [[0.1, 0.2]],
        }
        results = kb_with_fake.query_structured("câu", n_results=2)
        assert len(results) == 1
        assert results[0]["text"] == "Câu A."
