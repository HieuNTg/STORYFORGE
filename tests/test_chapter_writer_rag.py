"""Sprint 2 Task 1 — chapter_writer RAG integration tests."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from models.schemas import Character, ChapterOutline, PlotThread, WorldSetting


def _mk_config(rag_enabled=True, multi_query=True):
    pipeline = SimpleNamespace(
        rag_enabled=rag_enabled,
        rag_multi_query=multi_query,
        rag_per_char_queries=2,
        rag_per_thread_queries=2,
        rag_n_results_per_query=2,
        rag_merge_cap=5,
        rag_max_tokens=1000,
        rag_persist_dir="data/rag_test",
        rag_index_chapters=True,
        # Flags chapter_writer checks
        enable_voice_lock=False,
        enable_tiered_context=False,
        enable_chapter_contracts=False,
        enable_proactive_constraints=False,
        enable_thread_enforcement=False,
        enable_l1_causal_graph=False,
        enable_emotional_memory=False,
        enable_foreshadowing_enforcement=False,
        enable_scene_decomposition=False,
        enable_chapter_critique=False,
    )
    return SimpleNamespace(pipeline=pipeline)


def _mk_outline(ch=5, summary="Linh gặp An tại bến tàu."):
    return ChapterOutline(
        chapter_number=ch, title=f"Ch{ch}", summary=summary,
        key_events=["meeting"], emotional_arc="tension",
    )


def _mk_chars():
    return [
        Character(name="Linh", role="protagonist", personality="determined",
                  background="từ miền quê", motivation="tìm sự thật"),
        Character(name="An", role="antagonist", personality="mysterious",
                  background="nhà giàu", motivation="giữ bí mật"),
    ]


class _FakeRagKB:
    def __init__(self, results=None, available=True):
        self.is_available = available
        self._results = results or []
        self.query_structured_calls = 0
        self.query_calls = 0

    def query_structured(self, question, n_results=5, where=None, exclude_chapter=None):
        self.query_structured_calls += 1
        return list(self._results)[:n_results]

    def query(self, question, n_results=3):
        self.query_calls += 1
        return [r.get("text", "") for r in self._results[:n_results]]


class TestChapterWriterRag:
    def test_multi_query_path_injects_rag_block(self):
        from pipeline.layer1_story.chapter_writer import build_chapter_prompt
        results = [{
            "text": "Chương 2: Linh phát hiện bức thư cũ.",
            "metadata": {"chapter_number": 2, "chunk_index": 0, "characters": "Linh"},
            "distance": 0.1,
        }]
        kb = _FakeRagKB(results=results)
        _, user = build_chapter_prompt(
            config=_mk_config(rag_enabled=True, multi_query=True),
            title="t", genre="g", style="s",
            characters=_mk_chars(), world=WorldSetting(name="W", description="d"),
            outline=_mk_outline(ch=5), word_count=1000,
            context=None, rag_kb=kb,
            open_threads=[PlotThread(thread_id="t1", title="letter_mystery", description="Bức thư bí ẩn", planted_chapter=1)],
        )
        assert "bức thư cũ" in user
        # multi-query path hits query_structured, not legacy query
        assert kb.query_structured_calls >= 1
        assert kb.query_calls == 0

    def test_legacy_single_query_path(self):
        from pipeline.layer1_story.chapter_writer import build_chapter_prompt
        results = [{"text": "Ch1 content snippet.", "metadata": {}, "distance": 0.0}]
        kb = _FakeRagKB(results=results)
        _, user = build_chapter_prompt(
            config=_mk_config(rag_enabled=True, multi_query=False),
            title="t", genre="g", style="s",
            characters=_mk_chars(), world=WorldSetting(name="W", description="d"),
            outline=_mk_outline(), word_count=1000,
            context=None, rag_kb=kb,
        )
        assert "Ch1 content snippet." in user
        assert kb.query_calls == 1
        assert kb.query_structured_calls == 0

    def test_rag_disabled_skips_retrieval(self):
        from pipeline.layer1_story.chapter_writer import build_chapter_prompt
        kb = _FakeRagKB(results=[{"text": "x", "metadata": {}, "distance": 0.0}])
        _, user = build_chapter_prompt(
            config=_mk_config(rag_enabled=False),
            title="t", genre="g", style="s",
            characters=_mk_chars(), world=WorldSetting(name="W", description="d"),
            outline=_mk_outline(), word_count=1000,
            context=None, rag_kb=kb,
        )
        assert kb.query_structured_calls == 0
        assert kb.query_calls == 0

    def test_kb_unavailable_skips(self):
        from pipeline.layer1_story.chapter_writer import build_chapter_prompt
        kb = _FakeRagKB(available=False, results=[{"text": "x", "metadata": {}, "distance": 0}])
        _, user = build_chapter_prompt(
            config=_mk_config(rag_enabled=True),
            title="t", genre="g", style="s",
            characters=_mk_chars(), world=WorldSetting(name="W", description="d"),
            outline=_mk_outline(), word_count=1000,
            context=None, rag_kb=kb,
        )
        assert kb.query_structured_calls == 0
        assert kb.query_calls == 0


class TestBatchGeneratorIndexing:
    def test_index_chapter_into_rag_disabled_returns_zero(self):
        from pipeline.layer1_story.batch_generator import _index_chapter_into_rag
        from models.schemas import Chapter

        config = _mk_config(rag_enabled=False)
        ch = Chapter(chapter_number=1, title="t", content="content", word_count=1)
        outline = _mk_outline(ch=1)
        assert _index_chapter_into_rag(config, ch, outline, _mk_chars(), None) == 0

    def test_index_chapter_into_rag_calls_kb(self, monkeypatch):
        from pipeline.layer1_story import batch_generator
        from models.schemas import Chapter

        indexed = {}

        class _KB:
            is_available = True
            def index_chapter(self, chapter_number, content, characters, threads, summary):
                indexed.update(
                    chapter_number=chapter_number, content=content,
                    characters=characters, threads=threads, summary=summary,
                )
                return 3

        monkeypatch.setattr(
            "pipeline.layer1_story.context_helpers.get_rag_kb",
            lambda _: _KB(),
        )

        config = _mk_config(rag_enabled=True)
        ch = Chapter(chapter_number=7, title="t", content="some text.", word_count=2)
        outline = _mk_outline(ch=7, summary="meeting by the dock")
        threads = [PlotThread(thread_id="t1", title="letter_mystery", description="d", planted_chapter=1)]
        n = batch_generator._index_chapter_into_rag(config, ch, outline, _mk_chars(), threads)
        assert n == 3
        assert indexed["chapter_number"] == 7
        assert "Linh" in indexed["characters"]
        assert "An" in indexed["characters"]
        assert indexed["threads"] == ["t1"]
        assert indexed["summary"] == "meeting by the dock"

    def test_index_failure_is_nonfatal(self, monkeypatch):
        from pipeline.layer1_story import batch_generator
        from models.schemas import Chapter

        class _KB:
            is_available = True
            def index_chapter(self, **kwargs):
                raise RuntimeError("boom")

        monkeypatch.setattr(
            "pipeline.layer1_story.context_helpers.get_rag_kb",
            lambda _: _KB(),
        )
        config = _mk_config(rag_enabled=True)
        ch = Chapter(chapter_number=1, title="t", content="x", word_count=1)
        # Should not raise
        assert batch_generator._index_chapter_into_rag(
            config, ch, _mk_outline(ch=1), _mk_chars(), None,
        ) == 0
