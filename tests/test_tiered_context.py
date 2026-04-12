"""Tests for Phase 4: Tiered Context Builder — 4-tier system + priority promotion."""

from models.schemas import (
    Chapter, ChapterOutline, PlotThread, StoryBible, StructuredSummary,
)
from pipeline.layer1_story.tiered_context_builder import (
    build_tiered_context,
    _get_promoted_chapters,
    _get_detailed_summary,
)


def _chapter(num, summary="", content="", structured=None):
    return Chapter(
        chapter_number=num, title=f"Ch{num}", content=content,
        summary=summary, structured_summary=structured,
    )


def _outline(num, chars=None):
    return ChapterOutline(
        chapter_number=num, title=f"Outline {num}", summary=f"Outline summary {num}",
        characters_involved=chars or [],
    )


def _thread(tid="t1", status="open", last=1):
    return PlotThread(
        thread_id=tid, description=f"Thread {tid}",
        planted_chapter=1, status=status, last_mentioned_chapter=last,
    )


def _structured(events=None, chars=None, emotional="", hook=""):
    return StructuredSummary(
        plot_critical_events=events or [],
        character_developments=chars or [],
        emotional_shift=emotional,
        chapter_ending_hook=hook,
    )


class TestBuildTieredContext:
    def test_empty_chapters_returns_empty(self):
        result = build_tiered_context(1, [], _outline(1))
        assert result == ""

    def test_tier1_includes_last_2_chapters(self):
        texts = ["text ch1", "text ch2", "text ch3"]
        chapters = [_chapter(i + 1) for i in range(3)]
        result = build_tiered_context(4, chapters, _outline(4), all_chapter_texts=texts)
        assert "TIER 1" in result
        assert "Chương 2" in result or "Chương 3" in result

    def test_tier1_caps_text_at_2000(self):
        long_text = "x" * 5000
        chapters = [_chapter(1)]
        result = build_tiered_context(2, chapters, _outline(2), all_chapter_texts=[long_text])
        tier1_section = result.split("TIER 1")[1] if "TIER 1" in result else ""
        assert len(tier1_section) < 3000

    def test_tier2_detailed_summaries(self):
        chapters = []
        for i in range(1, 11):
            ss = _structured(events=[f"event_{i}"], chars=[f"dev_{i}"], emotional="tense")
            chapters.append(_chapter(i, summary=f"Summary ch{i}", structured=ss))
        result = build_tiered_context(
            10, chapters, _outline(10), all_chapter_texts=["t"] * 9
        )
        assert "TIER 2" in result

    def test_tier3_key_events(self):
        chapters = []
        for i in range(1, 20):
            ss = _structured(events=[f"critical_event_{i}"])
            chapters.append(_chapter(i, structured=ss))
        result = build_tiered_context(
            20, chapters, _outline(20), all_chapter_texts=["t"] * 19
        )
        assert "TIER 3" in result

    def test_tier4_bible_context(self):
        bible = StoryBible(
            premise="Epic fantasy premise",
            world_rules=["Rule 1", "Rule 2"],
            milestone_events=["Ch1: Start", "Ch5: Twist"],
        )
        result = build_tiered_context(5, [], _outline(5), story_bible=bible)
        assert "TIER 4" in result
        assert "Epic fantasy" in result
        assert "Rule 1" in result

    def test_token_budget_respected(self):
        texts = ["x" * 2000] * 10
        chapters = [_chapter(i + 1) for i in range(10)]
        result = build_tiered_context(
            11, chapters, _outline(11), all_chapter_texts=texts, max_tokens=100
        )
        assert len(result) // 4 <= 200  # some margin for headers

    def test_chapter_1_returns_bible_only(self):
        bible = StoryBible(premise="Test premise")
        result = build_tiered_context(1, [], _outline(1), story_bible=bible)
        assert "Test premise" in result
        assert "TIER 1" not in result


class TestPromotedChapters:
    def test_character_overlap_promotes(self):
        ss = _structured(chars=["Alice"])
        chapters = {5: _chapter(5, summary="Alice does things", structured=ss)}
        outline = _outline(10, chars=["Alice"])
        promoted = _get_promoted_chapters(10, outline, chapters, [], 5)
        assert 5 in promoted

    def test_summary_substring_promotes(self):
        chapters = {3: _chapter(3, summary="Bob went to market")}
        outline = _outline(10, chars=["Bob"])
        promoted = _get_promoted_chapters(10, outline, chapters, [], 5)
        assert 3 in promoted

    def test_thread_last_mentioned_promotes(self):
        thread = _thread("t1", status="open", last=4)
        chapters = {4: _chapter(4)}
        outline = _outline(10)
        promoted = _get_promoted_chapters(10, outline, chapters, [thread], 5)
        assert 4 in promoted

    def test_resolved_thread_not_promoted(self):
        thread = _thread("t1", status="resolved", last=4)
        outline = _outline(10)
        promoted = _get_promoted_chapters(10, outline, {4: _chapter(4)}, [thread], 5)
        assert 4 not in promoted

    def test_max_promotions_cap(self):
        chapters = {}
        for i in range(1, 10):
            chapters[i] = _chapter(i, summary="Alice here")
        outline = _outline(10, chars=["Alice"])
        promoted = _get_promoted_chapters(10, outline, chapters, [], max_promotions=3)
        assert len(promoted) <= 3

    def test_no_promote_current_or_future(self):
        chapters = {10: _chapter(10, summary="Alice"), 11: _chapter(11, summary="Alice")}
        outline = _outline(10, chars=["Alice"])
        promoted = _get_promoted_chapters(10, outline, chapters, [], 5)
        assert 10 not in promoted
        assert 11 not in promoted


class TestDetailedSummary:
    def test_structured_summary_used(self):
        ss = _structured(events=["battle"], chars=["growth"], emotional="intense", hook="cliffhanger")
        ch = _chapter(1, structured=ss)
        result = _get_detailed_summary(ch)
        assert "battle" in result
        assert "growth" in result
        assert "intense" in result
        assert "cliffhanger" in result

    def test_fallback_to_plain_summary(self):
        ch = _chapter(1, summary="Plain summary text")
        result = _get_detailed_summary(ch)
        assert result == "Plain summary text"

    def test_no_summary_returns_empty(self):
        ch = _chapter(1)
        result = _get_detailed_summary(ch)
        assert result == ""

    def test_caps_at_500_chars(self):
        ss = _structured(events=["e" * 200] * 5)
        ch = _chapter(1, structured=ss)
        result = _get_detailed_summary(ch)
        assert len(result) <= 500
