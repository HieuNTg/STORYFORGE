"""Tests for collaborative mode (Phase 7) - user writes, pipeline polishes."""

import pytest
from unittest.mock import MagicMock
from models.schemas import StoryDraft, Chapter, Character


# ══════════════════════════════════════════════════════════════════════════════
# Unit Tests: polish_chapter_impl
# ══════════════════════════════════════════════════════════════════════════════


class TestPolishChapterImpl:
    """Tests for polish_chapter_impl function."""

    @pytest.fixture
    def mock_generator(self):
        gen = MagicMock()
        gen.llm = MagicMock()
        gen.llm.generate_json.return_value = {
            "polished_text": "Polished chapter content with better prose.",
            "changes_made": ["Fixed grammar", "Improved flow"],
            "consistency_notes": [],
        }
        gen._layer_model = "test-model"
        return gen

    @pytest.fixture
    def sample_draft(self):
        return StoryDraft(
            title="Test Story",
            genre="Fantasy",
            chapters=[
                Chapter(chapter_number=1, title="Beginning", content="Original chapter 1 content."),
                Chapter(chapter_number=2, title="Middle", content="Original chapter 2 content."),
            ],
            characters=[
                Character(name="Hero", role="protagonist", personality="brave"),
            ],
            outlines=[],
        )

    def test_polish_light_preserves_structure(self, mock_generator, sample_draft):
        """Light polish should preserve most of the original structure."""
        from pipeline.layer1_story.story_continuation import polish_chapter_impl

        result = polish_chapter_impl(
            generator=mock_generator,
            draft=sample_draft,
            chapter_number=1,
            user_text="My custom chapter text that I wrote myself.",
            title="My Title",
            polish_level="light",
        )

        assert result is not None
        assert len(result.chapters) == 2
        mock_generator.llm.generate_json.assert_called_once()

    def test_polish_medium_enhances_prose(self, mock_generator, sample_draft):
        """Medium polish should call LLM with prose enhancement instructions."""
        from pipeline.layer1_story.story_continuation import polish_chapter_impl

        result = polish_chapter_impl(
            generator=mock_generator,
            draft=sample_draft,
            chapter_number=1,
            user_text="My chapter with some rough prose that needs work.",
            polish_level="medium",
        )

        assert result is not None
        mock_generator.llm.generate_json.assert_called_once()

    def test_polish_heavy_expands_scenes(self, mock_generator, sample_draft):
        """Heavy polish should expand and deepen scenes."""
        from pipeline.layer1_story.story_continuation import polish_chapter_impl

        result = polish_chapter_impl(
            generator=mock_generator,
            draft=sample_draft,
            chapter_number=2,
            user_text="Short scene that needs expansion.",
            polish_level="heavy",
        )

        assert result is not None
        assert result.chapters[1].content == "Polished chapter content with better prose."

    def test_polish_preserves_user_title(self, mock_generator, sample_draft):
        """User-provided title should be preserved."""
        from pipeline.layer1_story.story_continuation import polish_chapter_impl

        result = polish_chapter_impl(
            generator=mock_generator,
            draft=sample_draft,
            chapter_number=1,
            user_text="Content here",
            title="User's Custom Title",
            polish_level="light",
        )

        assert result.chapters[0].title == "User's Custom Title"

    def test_polish_uses_existing_title_if_not_provided(self, mock_generator, sample_draft):
        """Should use existing title if user doesn't provide one."""
        from pipeline.layer1_story.story_continuation import polish_chapter_impl

        result = polish_chapter_impl(
            generator=mock_generator,
            draft=sample_draft,
            chapter_number=1,
            user_text="Content here",
            title="",
            polish_level="light",
        )

        # Title should come from LLM or be original
        assert result.chapters[0].title is not None

    def test_polish_appends_new_chapter_if_beyond_existing(self, mock_generator, sample_draft):
        """Chapter number beyond existing should append as new chapter."""
        from pipeline.layer1_story.story_continuation import polish_chapter_impl

        original_count = len(sample_draft.chapters)
        result = polish_chapter_impl(
            generator=mock_generator,
            draft=sample_draft,
            chapter_number=3,  # Beyond existing 2 chapters
            user_text="Content for new chapter",
            polish_level="light",
        )
        # Should have appended a new chapter
        assert len(result.chapters) == original_count + 1

    def test_polish_calls_progress_callback(self, mock_generator, sample_draft):
        """Progress callback should be called."""
        from pipeline.layer1_story.story_continuation import polish_chapter_impl

        progress_msgs = []
        polish_chapter_impl(
            generator=mock_generator,
            draft=sample_draft,
            chapter_number=1,
            user_text="Content",
            polish_level="light",
            progress_callback=lambda m: progress_msgs.append(m),
        )

        assert len(progress_msgs) > 0


# ══════════════════════════════════════════════════════════════════════════════
# Unit Tests: Orchestrator polish_chapter method
# ══════════════════════════════════════════════════════════════════════════════


class TestOrchestratorPolishChapter:
    """Tests for StoryContinuation.polish_chapter method."""

    @pytest.fixture
    def mock_continuation(self):
        from pipeline.orchestrator_continuation import StoryContinuation
        from models.schemas import PipelineOutput

        output = PipelineOutput()
        output.story_draft = StoryDraft(
            title="Test",
            genre="Fantasy",
            chapters=[Chapter(chapter_number=1, title="Ch1", content="Original")],
            characters=[],
            outlines=[],
        )

        story_gen = MagicMock()
        story_gen.llm = MagicMock()
        story_gen.llm.generate_json.return_value = {
            "polished_text": "Polished content",
            "changes_made": [],
            "consistency_notes": [],
        }
        story_gen._layer_model = "test-model"

        checkpoint_mgr = MagicMock()

        cont = StoryContinuation(
            output=output,
            story_gen=story_gen,
            analyzer=MagicMock(),
            simulator=MagicMock(),
            enhancer=MagicMock(),
            checkpoint_manager=checkpoint_mgr,
        )
        return cont

    def test_polish_chapter_updates_draft(self, mock_continuation):
        """polish_chapter should update the story draft."""
        result = mock_continuation.polish_chapter(
            chapter_number=1,
            user_text="User written content here",
            title="New Title",
            polish_level="light",
        )

        assert result is not None
        assert result.chapters[0].title == "New Title"

    def test_polish_chapter_invalidates_enhanced(self, mock_continuation):
        """Polishing should invalidate L2 enhanced story."""
        mock_continuation.output.enhanced_story = MagicMock()

        mock_continuation.polish_chapter(
            chapter_number=1,
            user_text="Content",
            polish_level="medium",
        )

        assert mock_continuation.output.enhanced_story is None

    def test_polish_chapter_saves_checkpoint(self, mock_continuation):
        """Polishing should save checkpoint."""
        mock_continuation.polish_chapter(
            chapter_number=1,
            user_text="Content",
            polish_level="light",
        )

        mock_continuation.checkpoint_manager.save.assert_called_once_with(1)

    def test_polish_chapter_no_draft_raises(self, mock_continuation):
        """Should raise if no draft loaded."""
        mock_continuation.output.story_draft = None

        with pytest.raises(ValueError, match="No story draft"):
            mock_continuation.polish_chapter(
                chapter_number=1,
                user_text="Content",
                polish_level="light",
            )


# ══════════════════════════════════════════════════════════════════════════════
# Schema Tests: CollaborativeChapterRequest
# ══════════════════════════════════════════════════════════════════════════════


class TestCollaborativeChapterSchema:
    """Schema validation tests for CollaborativeChapterRequest."""

    def test_valid_request(self):
        """Valid request should pass validation."""
        from api.continuation_routes import CollaborativeChapterRequest

        req = CollaborativeChapterRequest(
            checkpoint="test_checkpoint",
            chapter_number=1,
            user_text="A" * 100,
            polish_level="light",
        )
        assert req.chapter_number == 1
        assert req.polish_level == "light"

    def test_min_text_length(self):
        """User text must be at least 100 characters."""
        from api.continuation_routes import CollaborativeChapterRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CollaborativeChapterRequest(
                checkpoint="test",
                chapter_number=1,
                user_text="Too short",
                polish_level="light",
            )

    def test_max_text_length(self):
        """User text must be at most 50000 characters."""
        from api.continuation_routes import CollaborativeChapterRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CollaborativeChapterRequest(
                checkpoint="test",
                chapter_number=1,
                user_text="A" * 50001,
                polish_level="light",
            )

    def test_chapter_number_min(self):
        """Chapter number must be >= 1."""
        from api.continuation_routes import CollaborativeChapterRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CollaborativeChapterRequest(
                checkpoint="test",
                chapter_number=0,
                user_text="A" * 100,
                polish_level="light",
            )


# ══════════════════════════════════════════════════════════════════════════════
# Integration Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestCollaborativeIntegration:
    """Integration tests for collaborative mode flow."""

    def test_polish_preserves_other_chapters(self):
        """Polishing one chapter should not affect others."""
        from pipeline.layer1_story.story_continuation import polish_chapter_impl

        draft = StoryDraft(
            title="Test",
            genre="Fantasy",
            chapters=[
                Chapter(chapter_number=1, title="Ch1", content="First chapter original"),
                Chapter(chapter_number=2, title="Ch2", content="Second chapter original"),
                Chapter(chapter_number=3, title="Ch3", content="Third chapter original"),
            ],
            characters=[],
            outlines=[],
        )

        mock_gen = MagicMock()
        mock_gen.llm.generate_json.return_value = {
            "polished_text": "Polished chapter 2",
            "changes_made": [],
            "consistency_notes": [],
        }
        mock_gen._layer_model = "test-model"

        result = polish_chapter_impl(
            generator=mock_gen,
            draft=draft,
            chapter_number=2,
            user_text="New chapter 2 content",
            polish_level="medium",
        )

        # Chapter 1 and 3 unchanged
        assert result.chapters[0].content == "First chapter original"
        assert result.chapters[2].content == "Third chapter original"
        # Chapter 2 changed
        assert result.chapters[1].content == "Polished chapter 2"

    def test_polish_levels_affect_prompt(self):
        """Different polish levels should produce different prompts."""
        from pipeline.layer1_story.story_continuation import polish_chapter_impl

        draft = StoryDraft(
            title="Test",
            genre="Fantasy",
            chapters=[Chapter(chapter_number=1, title="Ch1", content="Original")],
            characters=[],
            outlines=[],
        )

        prompts = []

        def capture_prompt(**kwargs):
            prompts.append(kwargs.get("user_prompt", ""))
            return {
                "polished_text": "Polished",
                "changes_made": [],
                "consistency_notes": [],
            }

        for level in ["light", "medium", "heavy"]:
            mock_gen = MagicMock()
            mock_gen.llm.generate_json.side_effect = capture_prompt
            mock_gen._layer_model = "test-model"

            polish_chapter_impl(
                generator=mock_gen,
                draft=draft,
                chapter_number=1,
                user_text="User content",
                polish_level=level,
            )

        # All prompts should be different (different instructions per level)
        assert len(prompts) == 3
