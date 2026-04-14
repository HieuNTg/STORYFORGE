"""Tests for SmartRevisionService — auto-detect and fix weak chapters."""

from unittest.mock import patch


from models.schemas import (
    AgentReview,
    Chapter,
    ChapterScore,
    EnhancedStory,
    StoryScore,
)


# ── Fixtures ─────────────────────────────────────────────────────────────

def _make_chapters(n=3):
    return [
        Chapter(
            chapter_number=i,
            title=f"Chương {i}",
            content=f"Nội dung chương {i}. " * 30,
            word_count=150,
        )
        for i in range(1, n + 1)
    ]


def _make_enhanced(n=3):
    return EnhancedStory(
        title="Test Story",
        genre="Hành động",
        chapters=_make_chapters(n),
        drama_score=0.5,
    )


def _make_chapter_score(ch_num, overall):
    cs = ChapterScore(chapter_number=ch_num)
    cs.overall = overall
    return cs


def _make_story_score(chapter_scores):
    return StoryScore(
        chapter_scores=chapter_scores,
        scoring_layer=2,
        weakest_chapter=min(chapter_scores, key=lambda s: s.overall).chapter_number if chapter_scores else 0,
    )


def _make_review(name, score, issues=None, suggestions=None):
    return AgentReview(
        agent_role=name,
        agent_name=name,
        score=score,
        issues=issues or [],
        suggestions=suggestions or [],
        approved=score >= 0.6,
        layer=2,
        iteration=1,
    )


# ── Tests ────────────────────────────────────────────────────────────────

class TestSmartRevision:

    def test_identifies_weak_chapters(self):
        """Only chapters below threshold should be flagged for revision."""
        from services.smart_revision import SmartRevisionService

        svc = SmartRevisionService(threshold=3.5, max_passes=2)
        enhanced = _make_enhanced(3)
        scores = _make_story_score([
            _make_chapter_score(1, 2.5),  # weak
            _make_chapter_score(2, 4.0),  # good
            _make_chapter_score(3, 3.0),  # weak
        ])

        # Mock LLM to return revised content, mock scorer to return improved score
        with patch.object(svc.llm, "generate", return_value="Revised content. " * 30) as mock_llm, \
             patch.object(svc.scorer, "score_chapter") as mock_scorer:
            # Return improved score for both weak chapters
            improved = ChapterScore(chapter_number=1)
            improved.overall = 4.0
            mock_scorer.return_value = improved

            result = svc.revise_weak_chapters(enhanced, [scores], [], genre="Hành động")

            assert result["total_weak"] == 2
            # LLM should only be called for weak chapters (1 and 3), not chapter 2
            assert mock_llm.call_count == 2

    def test_revision_improves_score(self):
        """When LLM revision improves score by >= MIN_DELTA, chapter content should be updated."""
        from services.smart_revision import SmartRevisionService

        svc = SmartRevisionService(threshold=3.5)
        enhanced = _make_enhanced(1)
        original_content = enhanced.chapters[0].content
        scores = _make_story_score([_make_chapter_score(1, 2.5)])

        revised_text = "Nội dung đã được cải thiện rất nhiều. " * 30

        with patch.object(svc.llm, "generate", return_value=revised_text), \
             patch.object(svc.scorer, "score_chapter") as mock_scorer:
            improved = ChapterScore(chapter_number=1)
            improved.overall = 4.0  # delta = +1.5 >= 0.3
            mock_scorer.return_value = improved

            result = svc.revise_weak_chapters(enhanced, [scores], [])

        assert result["revised_count"] == 1
        assert enhanced.chapters[0].content == revised_text
        assert enhanced.chapters[0].content != original_content
        assert result["score_deltas"][0]["delta"] == 1.5

    def test_revision_rejected_if_no_improvement(self):
        """When revision doesn't improve enough, original content is kept."""
        from services.smart_revision import SmartRevisionService

        svc = SmartRevisionService(threshold=3.5)
        enhanced = _make_enhanced(1)
        original_content = enhanced.chapters[0].content
        scores = _make_story_score([_make_chapter_score(1, 2.5)])

        with patch.object(svc.llm, "generate", return_value="Slightly changed. " * 30), \
             patch.object(svc.scorer, "score_chapter") as mock_scorer:
            # Score barely improves (delta = +0.1 < MIN_IMPROVEMENT_DELTA 0.3)
            barely = ChapterScore(chapter_number=1)
            barely.overall = 2.6
            mock_scorer.return_value = barely

            result = svc.revise_weak_chapters(enhanced, [scores], [])

        assert result["revised_count"] == 0
        assert enhanced.chapters[0].content == original_content

    def test_max_passes_respected(self):
        """LLM should be called at most max_passes times per chapter when revision fails."""
        from services.smart_revision import SmartRevisionService

        svc = SmartRevisionService(threshold=3.5, max_passes=2)
        enhanced = _make_enhanced(1)
        scores = _make_story_score([_make_chapter_score(1, 2.0)])

        with patch.object(svc.llm, "generate", return_value="Revised. " * 30) as mock_llm, \
             patch.object(svc.scorer, "score_chapter") as mock_scorer:
            # Always return low score — revision never accepted
            low = ChapterScore(chapter_number=1)
            low.overall = 2.1  # delta = +0.1 < 0.3
            mock_scorer.return_value = low

            result = svc.revise_weak_chapters(enhanced, [scores], [])

            # Should retry up to max_passes=2 times, then give up
            assert mock_llm.call_count == 2
            assert result["revised_count"] == 0

    def test_no_revision_when_all_pass(self):
        """When all chapters score above threshold, no LLM calls should be made."""
        from services.smart_revision import SmartRevisionService

        svc = SmartRevisionService(threshold=3.5)
        enhanced = _make_enhanced(3)
        scores = _make_story_score([
            _make_chapter_score(1, 4.0),
            _make_chapter_score(2, 4.5),
            _make_chapter_score(3, 3.8),
        ])

        with patch.object(svc.llm, "generate") as mock_llm:
            result = svc.revise_weak_chapters(enhanced, [scores], [])

        assert result["revised_count"] == 0
        assert result["total_weak"] == 0
        mock_llm.assert_not_called()

    def test_aggregate_review_guidance(self):
        """_aggregate_review_guidance should return relevant issues/suggestions capped at 5."""
        from services.smart_revision import SmartRevisionService

        svc = SmartRevisionService()
        reviews = [
            _make_review("agent_a", 0.4,
                         issues=["Chương 1 thiếu xung đột", "Vấn đề chung"],
                         suggestions=["Ch1 cần thêm đối thoại"]),
            _make_review("agent_b", 0.5,
                         issues=["Chương 2 quá dài", "Lỗi liên tục chương 1"],
                         suggestions=["Tăng kịch tính chương 1"]),
            _make_review("agent_c", 0.8,
                         issues=["Chương 3 ổn"],
                         suggestions=["Chương 3 tốt rồi"]),
        ]

        issues, suggestions = svc._aggregate_review_guidance(1, reviews)

        # Should find chapter-1-specific issues + general from low-score agents
        assert len(issues) <= 5
        assert len(suggestions) <= 5
        # Chapter 1 specific issues should be included (regex matching)
        assert any("chương 1" in i.lower() or "ch1" in i.lower() for i in issues)

    def test_graceful_on_empty_scores(self):
        """No crash when quality_scores list is empty."""
        from services.smart_revision import SmartRevisionService

        svc = SmartRevisionService()
        enhanced = _make_enhanced(1)

        result = svc.revise_weak_chapters(enhanced, [], [])

        assert result["revised_count"] == 0
        assert result["total_weak"] == 0

    def test_config_fields_exist(self):
        """PipelineConfig should have smart revision fields."""
        from config import PipelineConfig

        pc = PipelineConfig()
        assert hasattr(pc, "enable_smart_revision")
        assert hasattr(pc, "smart_revision_threshold")
        assert pc.enable_smart_revision is True
        assert pc.smart_revision_threshold == 3.5
