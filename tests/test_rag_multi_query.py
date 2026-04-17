"""Sprint 2 Task 1 — build_rag_context multi-query retrieval unit tests."""
from __future__ import annotations

from types import SimpleNamespace

from pipeline.layer1_story.context_helpers import build_rag_context


class _FakeKB:
    """Records queries, returns canned results. Round-robin-ish by query text hash."""

    def __init__(self, results_by_query: dict[str, list[dict]] | None = None,
                 default_results: list[dict] | None = None,
                 available: bool = True):
        self.is_available = available
        self.results_by_query = results_by_query or {}
        self.default_results = default_results or []
        self.calls: list[dict] = []

    def query_structured(self, question, n_results=5, where=None, exclude_chapter=None):
        self.calls.append({
            "question": question, "n_results": n_results,
            "where": where, "exclude_chapter": exclude_chapter,
        })
        return list(self.results_by_query.get(question, self.default_results))[:n_results]


def _make_outline(ch_num=10, summary="Linh và An đối đầu tại bến tàu.", title="t"):
    return SimpleNamespace(chapter_number=ch_num, summary=summary, title=title)


def _hit(ch, chunk, dist=0.1, text=None):
    return {
        "text": text or f"chunk {ch}.{chunk}",
        "metadata": {"chapter_number": ch, "chunk_index": chunk, "characters": ""},
        "distance": dist,
    }


class TestBuildRagContext:
    def test_no_kb_returns_empty(self):
        assert build_rag_context(None, _make_outline()) == ""

    def test_kb_unavailable_returns_empty(self):
        assert build_rag_context(_FakeKB(available=False), _make_outline()) == ""

    def test_no_summary_returns_empty(self):
        assert build_rag_context(_FakeKB(), _make_outline(summary="")) == ""

    def test_dedup_by_chapter_and_chunk(self):
        hit_same = _hit(3, 0, dist=0.1)
        kb = _FakeKB(default_results=[hit_same])
        chars = [SimpleNamespace(name="Linh", role="protagonist", motivation="find truth")]
        out = build_rag_context(kb, _make_outline(), characters=chars)
        # The same (ch3, chunk0) chunk comes back for every query — must dedup to 1
        assert out.count("chunk 3.0") == 1

    def test_distance_ranking(self):
        kb = _FakeKB(results_by_query={
            "Linh và An đối đầu tại bến tàu.": [_hit(5, 0, dist=0.9, text="far")],
            "Linh: protect sister": [_hit(2, 1, dist=0.1, text="near")],
        }, default_results=[])
        chars = [SimpleNamespace(name="Linh", role="protagonist", motivation="protect sister")]
        out = build_rag_context(kb, _make_outline(), characters=chars, n_per_query=1)
        near_pos = out.index("near")
        far_pos = out.index("far")
        assert near_pos < far_pos

    def test_merge_cap(self):
        # Per-query unique hits — one query one chapter, so dedup keeps all
        results_by_query = {
            "Linh và An đối đầu tại bến tàu.": [_hit(1, 0, 0.1), _hit(1, 1, 0.2)],
            "Linh: g": [_hit(2, 0, 0.3), _hit(2, 1, 0.4)],
            "t1: d1": [_hit(3, 0, 0.5), _hit(3, 1, 0.6)],
        }
        kb = _FakeKB(results_by_query=results_by_query, default_results=[])
        chars = [SimpleNamespace(name="Linh", role="protagonist", motivation="g")]
        threads = [SimpleNamespace(title="t1", description="d1")]
        out = build_rag_context(kb, _make_outline(),
                                characters=chars, open_threads=threads, merge_cap=5)
        # 6 unique hits total, cap=5 → 5 items → 4 separators
        assert out.count("\n---\n") == 4

    def test_exclude_current_chapter_forwarded(self):
        kb = _FakeKB()
        build_rag_context(kb, _make_outline(ch_num=7))
        assert kb.calls[0]["exclude_chapter"] == 7

    def test_char_query_attaches_where_filter(self):
        kb = _FakeKB()
        chars = [SimpleNamespace(name="Linh", role="protagonist", motivation="goal")]
        build_rag_context(kb, _make_outline(), characters=chars)
        char_call = next(c for c in kb.calls if c["where"] is not None)
        assert char_call["where"] == {"characters": {"$contains": "Linh"}}

    def test_query_tag_in_output(self):
        kb = _FakeKB(default_results=[_hit(3, 0)])
        chars = [SimpleNamespace(name="Linh", role="protagonist", motivation="")]
        out = build_rag_context(kb, _make_outline(), characters=chars)
        assert "— summary]" in out or "— char_Linh]" in out

    def test_focus_char_fallback_when_no_priority_role(self):
        kb = _FakeKB()
        chars = [SimpleNamespace(name="A", role="side", motivation="")]
        build_rag_context(kb, _make_outline(), characters=chars, per_char_queries=3)
        # At least one call should carry a where filter for A
        assert any(c["where"] == {"characters": {"$contains": "A"}} for c in kb.calls)

    def test_empty_hits_returns_empty_string(self):
        kb = _FakeKB(default_results=[])
        assert build_rag_context(kb, _make_outline()) == ""
