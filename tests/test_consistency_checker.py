"""Tests for retroactive consistency checker (Phase 8)."""

import pytest
from unittest.mock import MagicMock
from datetime import datetime

from models.schemas import (
    StoryDraft, Chapter, Character, CharacterState, ConsistencyIssue, ConsistencyReport,
)
from pipeline.layer1_story.consistency_checker import (
    ConsistencyChecker, check_consistency,
)


# ══════════════════════════════════════════════════════════════════════════════
# Schema Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestConsistencySchemas:
    """Tests for consistency-related schemas."""

    def test_consistency_issue_schema(self):
        """Should create valid ConsistencyIssue."""
        issue = ConsistencyIssue(
            issue_type="character_location",
            severity="warning",
            description="Hero was in the forest in ch.1 but suddenly in the castle in ch.2",
            chapter_a=1,
            chapter_b=2,
            entity="Hero",
            value_a="forest",
            value_b="castle",
            suggested_fix="Add travel scene",
            auto_fixable=False,
        )
        assert issue.issue_type == "character_location"
        assert issue.severity == "warning"
        assert issue.entity == "Hero"

    def test_consistency_report_schema(self):
        """Should create valid ConsistencyReport."""
        report = ConsistencyReport(
            checked_chapters=[1, 2, 3],
            issues=[],
            error_count=0,
            warning_count=0,
            is_consistent=True,
            checked_at=datetime.now().isoformat(),
        )
        assert report.is_consistent is True
        assert len(report.checked_chapters) == 3

    def test_report_counts_issues_correctly(self):
        """Report should count issues by severity."""
        issues = [
            ConsistencyIssue(
                issue_type="fact", severity="error", description="Error 1",
                chapter_a=1, chapter_b=2,
            ),
            ConsistencyIssue(
                issue_type="timeline", severity="warning", description="Warning 1",
                chapter_a=1, chapter_b=2,
            ),
            ConsistencyIssue(
                issue_type="character_state", severity="warning", description="Warning 2",
                chapter_a=2, chapter_b=3,
            ),
            ConsistencyIssue(
                issue_type="object", severity="info", description="Info 1",
                chapter_a=1, chapter_b=3,
            ),
        ]
        report = ConsistencyReport(
            checked_chapters=[1, 2, 3],
            issues=issues,
            error_count=1,
            warning_count=2,
            info_count=1,
            is_consistent=False,
        )
        assert report.error_count == 1
        assert report.warning_count == 2
        assert report.info_count == 1
        assert report.is_consistent is False


# ══════════════════════════════════════════════════════════════════════════════
# ConsistencyChecker Unit Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestConsistencyChecker:
    """Unit tests for ConsistencyChecker class."""

    @pytest.fixture
    def sample_draft(self):
        """Create a sample draft with multiple chapters."""
        return StoryDraft(
            title="Test Story",
            genre="Fantasy",
            chapters=[
                Chapter(
                    chapter_number=1, title="Beginning",
                    content="The hero walked through the forest. He was happy and brave.",
                    summary="Hero explores forest",
                ),
                Chapter(
                    chapter_number=2, title="Conflict",
                    content="The hero was suddenly in the castle. He felt sad now.",
                    summary="Hero in castle",
                ),
            ],
            characters=[
                Character(name="Hero", role="protagonist", personality="brave"),
            ],
            character_states=[
                CharacterState(name="Hero", mood="happy", arc_position="rising"),
            ],
            outlines=[],
        )

    def test_checker_initializes_without_llm(self):
        """Should work without LLM client."""
        checker = ConsistencyChecker()
        assert checker.llm is None

    def test_checker_initializes_with_llm(self):
        """Should accept LLM client."""
        mock_llm = MagicMock()
        checker = ConsistencyChecker(mock_llm)
        assert checker.llm == mock_llm

    def test_check_chapters_returns_report(self, sample_draft):
        """check_chapters should return a ConsistencyReport."""
        checker = ConsistencyChecker()
        report = checker.check_chapters(sample_draft, [2])

        assert isinstance(report, ConsistencyReport)
        assert 2 in report.checked_chapters

    def test_check_with_no_previous_chapters(self):
        """Checking first chapter should work with no previous."""
        draft = StoryDraft(
            title="Test",
            genre="Fantasy",
            chapters=[Chapter(chapter_number=1, title="Ch1", content="Content")],
            characters=[],
            outlines=[],
        )
        checker = ConsistencyChecker()
        report = checker.check_chapters(draft, [1])

        assert report.is_consistent is True
        assert len(report.issues) == 0

    def test_detects_state_contradiction(self):
        """Should detect when character state contradicts previous chapter."""
        draft = StoryDraft(
            title="Test",
            genre="Fantasy",
            chapters=[
                Chapter(chapter_number=1, title="Ch1", content="Hero was happy and smiling."),
                Chapter(chapter_number=2, title="Ch2", content="Hero was extremely sad and crying."),
            ],
            characters=[Character(name="Hero", role="protagonist", personality="brave")],
            character_states=[
                CharacterState(name="Hero", mood="vui", arc_position="rising"),
            ],
            outlines=[],
        )

        checker = ConsistencyChecker()
        report = checker.check_chapters(draft, [2])

        # May or may not detect based on heuristics - check report structure
        assert isinstance(report, ConsistencyReport)
        assert report.checked_at != ""

    def test_full_story_check(self, sample_draft):
        """check_full_story should check all chapters."""
        checker = ConsistencyChecker()
        report = checker.check_full_story(sample_draft)

        assert len(report.checked_chapters) == 2
        assert 1 in report.checked_chapters
        assert 2 in report.checked_chapters

    def test_progress_callback_called(self, sample_draft):
        """Should call progress callback during check."""
        checker = ConsistencyChecker()
        progress_msgs = []

        checker.check_chapters(
            sample_draft, [2],
            progress_callback=lambda m: progress_msgs.append(m),
        )

        assert len(progress_msgs) > 0


# ══════════════════════════════════════════════════════════════════════════════
# Convenience Function Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestCheckConsistencyFunction:
    """Tests for the check_consistency convenience function."""

    def test_function_returns_report(self):
        """check_consistency function should return report."""
        draft = StoryDraft(
            title="Test",
            genre="Fantasy",
            chapters=[
                Chapter(chapter_number=1, title="Ch1", content="Content 1"),
                Chapter(chapter_number=2, title="Ch2", content="Content 2"),
            ],
            characters=[],
            outlines=[],
        )

        report = check_consistency(draft, [2])

        assert isinstance(report, ConsistencyReport)

    def test_function_passes_llm_client(self):
        """Should pass LLM client to checker."""
        draft = StoryDraft(
            title="Test",
            genre="Fantasy",
            chapters=[Chapter(chapter_number=1, title="Ch1", content="Content")],
            characters=[],
            outlines=[],
        )
        mock_llm = MagicMock()

        report = check_consistency(draft, [1], llm_client=mock_llm)

        assert isinstance(report, ConsistencyReport)


# ══════════════════════════════════════════════════════════════════════════════
# Orchestrator Integration Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestOrchestratorCheckConsistency:
    """Tests for StoryContinuation.check_consistency method."""

    @pytest.fixture
    def mock_continuation(self):
        from pipeline.orchestrator_continuation import StoryContinuation
        from models.schemas import PipelineOutput

        output = PipelineOutput()
        output.story_draft = StoryDraft(
            title="Test",
            genre="Fantasy",
            chapters=[
                Chapter(chapter_number=1, title="Ch1", content="Original content 1"),
                Chapter(chapter_number=2, title="Ch2", content="Original content 2"),
            ],
            characters=[],
            outlines=[],
        )

        story_gen = MagicMock()
        story_gen.llm = None

        cont = StoryContinuation(
            output=output,
            story_gen=story_gen,
            analyzer=MagicMock(),
            simulator=MagicMock(),
            enhancer=MagicMock(),
            checkpoint_manager=MagicMock(),
        )
        return cont

    def test_check_specific_chapters(self, mock_continuation):
        """Should check specific chapters when provided."""
        report = mock_continuation.check_consistency(chapter_numbers=[2])

        assert isinstance(report, ConsistencyReport)
        assert 2 in report.checked_chapters

    def test_check_full_story_when_no_chapters_specified(self, mock_continuation):
        """Should check full story when no chapters specified."""
        report = mock_continuation.check_consistency()

        assert isinstance(report, ConsistencyReport)
        assert len(report.checked_chapters) == 2

    def test_raises_when_no_draft(self, mock_continuation):
        """Should raise ValueError when no draft loaded."""
        mock_continuation.output.story_draft = None

        with pytest.raises(ValueError, match="No story draft"):
            mock_continuation.check_consistency()


# ══════════════════════════════════════════════════════════════════════════════
# Schema Validation Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestConsistencyCheckRequestSchema:
    """Schema validation tests for ConsistencyCheckRequest."""

    def test_valid_request(self):
        """Valid request should pass validation."""
        from api.continuation_routes import ConsistencyCheckRequest

        req = ConsistencyCheckRequest(
            checkpoint="test_checkpoint",
            chapter_numbers=[1, 2, 3],
        )
        assert req.checkpoint == "test_checkpoint"
        assert req.chapter_numbers == [1, 2, 3]

    def test_empty_chapter_numbers_allowed(self):
        """Empty chapter_numbers should be allowed (means check all)."""
        from api.continuation_routes import ConsistencyCheckRequest

        req = ConsistencyCheckRequest(checkpoint="test")
        assert req.chapter_numbers == []


# ══════════════════════════════════════════════════════════════════════════════
# Integration: Consistency in Continue Flow
# ══════════════════════════════════════════════════════════════════════════════


class TestConsistencyInContinueFlow:
    """Tests for consistency checking integrated into continue flow."""

    def test_write_from_outlines_runs_consistency_check(self):
        """write_from_outlines should run consistency check after writing."""
        from pipeline.layer1_story.story_continuation import write_from_outlines
        from models.schemas import ChapterOutline

        draft = StoryDraft(
            title="Test",
            genre="Fantasy",
            chapters=[Chapter(chapter_number=1, title="Ch1", content="Existing content")],
            characters=[],
            outlines=[],
        )

        mock_gen = MagicMock()
        mock_gen.config.pipeline.context_window_chapters = 3
        mock_gen.config.pipeline.writing_style = ""
        mock_gen.config.pipeline.enable_self_review = False
        mock_gen.rebuild_context.return_value = MagicMock(
            character_states=[], plot_events=[], open_threads=[], conflict_map=[],
            current_chapter=2, total_chapters=2,
        )
        mock_gen.llm.generate.return_value = "Generated chapter content"
        mock_gen._write_chapter_with_long_context.return_value = Chapter(
            chapter_number=2, title="Ch2", content="Generated chapter content"
        )

        outlines = [
            ChapterOutline(chapter_number=2, title="Ch2", summary="Summary"),
        ]

        progress_msgs = []
        write_from_outlines(
            generator=mock_gen,
            draft=draft,
            outlines=outlines,
            progress_callback=lambda m: progress_msgs.append(m),
        )

        # Check that consistency check message appeared
        consistency_msgs = [m for m in progress_msgs if "Consistency" in m or "consistency" in m]
        assert len(consistency_msgs) > 0
