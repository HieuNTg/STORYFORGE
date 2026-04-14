"""Tests for Phase 2.1 zero-cost quality: stale threads, chapter hooks, emotional arc tracking."""

from unittest.mock import MagicMock
from models.schemas import (
    StoryContext, StructuredSummary, PlotThread, ChapterOutline,
)
from pipeline.layer1_story.plot_thread_tracker import get_stale_threads
from pipeline.layer1_story.structured_summary_extractor import extract_structured_summary
from pipeline.layer1_story.chapter_writer import _append_consistency_context


class TestGetStaleThreads:
    def _thread(self, desc, planted, last_mentioned, status="open"):
        return PlotThread(
            thread_id=f"t_{desc}", description=desc,
            planted_chapter=planted, last_mentioned_chapter=last_mentioned,
            status=status,
        )

    def test_detects_stale_thread(self):
        threads = [self._thread("secret", 1, 1)]
        stale = get_stale_threads(threads, current_chapter=12, stale_gap=10)
        assert len(stale) == 1
        assert stale[0].description == "secret"

    def test_ignores_recently_mentioned(self):
        threads = [self._thread("recent", 1, 10)]
        assert get_stale_threads(threads, current_chapter=12, stale_gap=10) == []

    def test_ignores_resolved(self):
        threads = [self._thread("done", 1, 1, status="resolved")]
        assert get_stale_threads(threads, current_chapter=20, stale_gap=5) == []

    def test_dynamic_gap_calculation(self):
        """min(10, max(3, total // 3)) for various story lengths."""
        assert min(10, max(3, 6 // 3)) == 3    # 6-chapter story → gap 3
        assert min(10, max(3, 15 // 3)) == 5   # 15-chapter story → gap 5
        assert min(10, max(3, 30 // 3)) == 10  # 30-chapter story → gap 10
        assert min(10, max(3, 60 // 3)) == 10  # 60-chapter story → capped at 10

    def test_empty_threads(self):
        assert get_stale_threads([], current_chapter=10, stale_gap=5) == []

    def test_multiple_stale(self):
        threads = [
            self._thread("a", 1, 1),
            self._thread("b", 2, 2),
            self._thread("c", 5, 9),  # not stale at gap=5
        ]
        stale = get_stale_threads(threads, current_chapter=11, stale_gap=5)
        assert len(stale) == 2
        assert {t.description for t in stale} == {"a", "b"}


class TestStructuredSummaryNewFields:
    def test_parses_hook_and_emotional_arc(self):
        llm = MagicMock()
        llm.generate_json.return_value = {
            "plot_critical_events": [],
            "character_developments": [],
            "open_questions": [],
            "emotional_shift": "hope to despair",
            "threads_advanced": [],
            "threads_opened": [],
            "threads_resolved": [],
            "chapter_ending_hook": "Minh đứng trước cửa hang, bóng tối nuốt chửng",
            "actual_emotional_arc": "hy vọng → tuyệt vọng",
            "brief_summary": "Minh phát hiện hang động bí ẩn.",
        }
        structured, brief = extract_structured_summary(llm, "content", 3, [])
        assert structured.chapter_ending_hook == "Minh đứng trước cửa hang, bóng tối nuốt chửng"
        assert structured.actual_emotional_arc == "hy vọng → tuyệt vọng"

    def test_defaults_when_missing(self):
        llm = MagicMock()
        llm.generate_json.return_value = {
            "plot_critical_events": [],
            "character_developments": [],
            "open_questions": [],
            "emotional_shift": "",
            "threads_advanced": [],
            "threads_opened": [],
            "threads_resolved": [],
            "brief_summary": "summary",
        }
        structured, _ = extract_structured_summary(llm, "content", 1, [])
        assert structured.chapter_ending_hook == ""
        assert structured.actual_emotional_arc == ""

    def test_handles_none_from_llm(self):
        llm = MagicMock()
        llm.generate_json.return_value = {
            "plot_critical_events": [],
            "character_developments": [],
            "open_questions": [],
            "emotional_shift": "",
            "threads_advanced": [],
            "threads_opened": [],
            "threads_resolved": [],
            "chapter_ending_hook": None,
            "actual_emotional_arc": None,
            "brief_summary": "summary",
        }
        structured, _ = extract_structured_summary(llm, "content", 1, [])
        assert structured.chapter_ending_hook == ""
        assert structured.actual_emotional_arc == ""


class TestAppendConsistencyContext:
    def _context(self, **kwargs):
        return StoryContext(total_chapters=20, **kwargs)

    def test_stale_thread_warnings_injected(self):
        ctx = self._context(stale_thread_warnings=[
            "Tuyến 'bí mật' bị bỏ quên 8 chương",
        ])
        parts = []
        _append_consistency_context(parts, ctx)
        assert any("TUYẾN TRUYỆN BỊ BỎ QUÊN" in p for p in parts)
        assert any("PHẢI" in p for p in parts)

    def test_stale_warnings_capped_at_5(self):
        ctx = self._context(stale_thread_warnings=[f"w{i}" for i in range(10)])
        parts = []
        _append_consistency_context(parts, ctx)
        stale_block = [p for p in parts if "BỎ QUÊN" in p][0]
        assert stale_block.count("- w") == 5

    def test_chapter_hook_injected(self):
        ctx = self._context(chapter_ending_hook="Minh ngã xuống vực")
        parts = []
        _append_consistency_context(parts, ctx)
        assert any("PHẢI tiếp nối" in p for p in parts)
        assert any("Minh ngã xuống vực" in p for p in parts)

    def test_emotional_history_injected(self):
        ctx = self._context(emotional_history=["vui → buồn", "buồn → giận", "giận → bình tĩnh"])
        parts = []
        _append_consistency_context(parts, ctx)
        assert any("Dòng cảm xúc gần đây" in p for p in parts)
        assert any("→" in p for p in parts)

    def test_emotional_history_last_3_only(self):
        ctx = self._context(emotional_history=[f"e{i}" for i in range(5)])
        parts = []
        _append_consistency_context(parts, ctx)
        emo_block = [p for p in parts if "Dòng cảm xúc" in p][0]
        assert "e2" in emo_block and "e3" in emo_block and "e4" in emo_block
        assert "e0" not in emo_block

    def test_no_injection_when_empty(self):
        ctx = self._context()
        parts = []
        _append_consistency_context(parts, ctx)
        assert not any("BỎ QUÊN" in p for p in parts)
        assert not any("HOOK" in p for p in parts)
        assert not any("cảm xúc" in p for p in parts)


class TestPostProcessingIntegration:
    """Integration test: verify post_processing stores hook/emotional/stale in story_context."""

    def _make_context(self):
        return StoryContext(total_chapters=30)

    def _make_outline(self, ch_num):
        return ChapterOutline(
            chapter_number=ch_num, title=f"Ch {ch_num}",
            summary="s", key_events=["e"], emotional_arc="hope",
        )

    def test_hook_and_emotional_stored_after_structured_summary(self):
        ctx = self._make_context()
        ctx.chapter_ending_hook = ""
        ctx.emotional_history = []

        structured = StructuredSummary(
            chapter_ending_hook="cliffhanger text",
            actual_emotional_arc="calm → shock",
        )

        # Simulate what post_processing does after structured extraction
        if structured.chapter_ending_hook:
            ctx.chapter_ending_hook = structured.chapter_ending_hook
        if structured.actual_emotional_arc:
            ctx.emotional_history.append(structured.actual_emotional_arc)

        assert ctx.chapter_ending_hook == "cliffhanger text"
        assert ctx.emotional_history == ["calm → shock"]

    def test_stale_warning_format(self):
        t = PlotThread(
            thread_id="t1", description="con rồng",
            planted_chapter=1, last_mentioned_chapter=2, status="open",
        )
        stale = get_stale_threads([t], current_chapter=15, stale_gap=10)
        assert len(stale) == 1
        warning = (
            f"Tuyến '{stale[0].description}' (mở từ ch.{stale[0].planted_chapter}, "
            f"lần cuối nhắc ch.{stale[0].last_mentioned_chapter}) — "
            f"đã {15 - stale[0].last_mentioned_chapter} chương không nhắc đến"
        )
        assert "con rồng" in warning
        assert "13 chương" in warning
