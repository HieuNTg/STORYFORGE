"""Tests for story continuation pipeline context wiring fixes."""

from unittest.mock import MagicMock, patch
from models.schemas import (
    StoryDraft, Character, Chapter,
    CharacterState, PlotEvent, StoryContext, ConflictEntry, ForeshadowingEntry,
    StoryBible,
)
from pipeline.layer1_story.generator import StoryGenerator


class TestRebuildContextConflictMap:
    """Verify rebuild_context restores conflict_map and open_threads from draft."""

    def _make_draft(self, with_conflict_web=True):
        draft = StoryDraft(
            title="Test", genre="fantasy",
            characters=[Character(name="A", role="hero", personality="brave", motivation="save world")],
            chapters=[
                Chapter(chapter_number=1, title="Ch1", content="content", word_count=100, summary="summary1"),
            ],
            character_states=[CharacterState(name="A", mood="happy", arc_position="rising", last_action="fought")],
            plot_events=[PlotEvent(chapter_number=1, event="battle")],
        )
        if with_conflict_web:
            draft.conflict_web = [
                ConflictEntry(
                    conflict_id="c1", conflict_type="external",
                    characters=["A", "B"],
                    description="rivalry", status="active",
                ),
            ]
            draft.foreshadowing_plan = [
                ForeshadowingEntry(
                    hint="dark omen",
                    plant_chapter=1, payoff_chapter=5,
                ),
            ]
        return draft

    def _make_generator(self):
        with patch("pipeline.layer1_story.generator.LLMClient"):
            gen = StoryGenerator.__new__(StoryGenerator)
            gen.config = MagicMock()
            gen.config.pipeline.context_window_chapters = 5
            gen.llm = MagicMock()
            return gen

    def test_rebuild_context_restores_conflict_map(self):
        gen = self._make_generator()
        draft = self._make_draft(with_conflict_web=True)
        ctx = gen.rebuild_context(draft)
        assert len(ctx.conflict_map) == 1
        assert ctx.conflict_map[0].conflict_id == "c1"

    def test_rebuild_context_empty_conflict_map_when_missing(self):
        gen = self._make_generator()
        draft = self._make_draft(with_conflict_web=False)
        ctx = gen.rebuild_context(draft)
        assert ctx.conflict_map == []

    def test_rebuild_context_initializes_open_threads(self):
        gen = self._make_generator()
        draft = self._make_draft()
        ctx = gen.rebuild_context(draft)
        assert ctx.open_threads == []

    def test_rebuild_context_preserves_existing_fields(self):
        gen = self._make_generator()
        draft = self._make_draft()
        ctx = gen.rebuild_context(draft)
        assert len(ctx.character_states) == 1
        assert len(ctx.plot_events) == 1
        assert len(ctx.recent_summaries) == 1


class TestContinuationParameterPassing:
    """Verify story_continuation passes correct params to process_chapter_post_write."""

    @patch("pipeline.layer1_story.story_continuation.process_chapter_post_write")
    def test_passes_draft_to_post_write(self, mock_post_write):
        """draft should be passed as positional arg (bible_enabled removed)."""
        from pipeline.layer1_story.story_continuation import continue_story

        draft = StoryDraft(
            title="T", genre="fantasy",
            characters=[Character(name="A", role="hero", personality="brave", motivation="m")],
            chapters=[Chapter(chapter_number=1, title="Ch1", content="c", word_count=100, summary="s")],
            story_bible=StoryBible(),
        )

        gen = MagicMock()
        gen.config.pipeline.context_window_chapters = 5
        gen.config.pipeline.enable_self_review = False
        gen.config.pipeline.writing_style = ""
        gen.rebuild_context.return_value = StoryContext(total_chapters=1, current_chapter=1)
        gen.llm.generate_json.return_value = {
            "outlines": [{"chapter_number": 2, "title": "Ch2", "summary": "s", "key_events": []}]
        }
        gen._layer_model = None
        gen._get_self_reviewer.return_value = None
        gen._write_chapter_with_long_context.return_value = Chapter(
            chapter_number=2, title="Ch2", content="new content", word_count=200
        )
        mock_post_write.return_value = (
            Chapter(chapter_number=2, title="Ch2", content="new content", word_count=200),
            "summary", [], [],
        )

        continue_story(gen, draft, additional_chapters=1)

        # bible_enabled removed; positional index 7 is now draft
        call_args = mock_post_write.call_args
        assert call_args[0][7] is draft

    @patch("pipeline.layer1_story.story_continuation.process_chapter_post_write")
    def test_passes_foreshadowing_plan_kwarg(self, mock_post_write):
        from pipeline.layer1_story.story_continuation import continue_story

        draft = StoryDraft(
            title="T", genre="fantasy",
            characters=[Character(name="A", role="hero", personality="brave", motivation="m")],
            chapters=[Chapter(chapter_number=1, title="Ch1", content="c", word_count=100, summary="s")],
            foreshadowing_plan=[
                ForeshadowingEntry(hint="omen", plant_chapter=1, payoff_chapter=3),
            ],
        )

        gen = MagicMock()
        gen.config.pipeline.context_window_chapters = 5
        gen.config.pipeline.enable_self_review = False
        gen.config.pipeline.writing_style = ""
        gen.rebuild_context.return_value = StoryContext(total_chapters=1, current_chapter=1)
        gen.llm.generate_json.return_value = {
            "outlines": [{"chapter_number": 2, "title": "Ch2", "summary": "s", "key_events": []}]
        }
        gen._layer_model = None
        gen._get_self_reviewer.return_value = None
        gen._write_chapter_with_long_context.return_value = Chapter(
            chapter_number=2, title="Ch2", content="content", word_count=200
        )
        mock_post_write.return_value = (
            Chapter(chapter_number=2, title="Ch2", content="content", word_count=200),
            "summary", [], [],
        )

        continue_story(gen, draft, additional_chapters=1)

        call_kwargs = mock_post_write.call_args[1]
        assert "foreshadowing_plan" in call_kwargs
        assert len(call_kwargs["foreshadowing_plan"]) == 1
        assert call_kwargs["foreshadowing_plan"][0].hint == "omen"


class TestBuildSystemPrompt:
    """Test _build_system_prompt in branch_routes."""

    def test_empty_context_returns_base_prompt(self):
        from api.branch_routes import _build_system_prompt
        prompt = _build_system_prompt({})
        assert "creative storyteller" in prompt
        assert "Return JSON" in prompt

    def test_genre_included(self):
        from api.branch_routes import _build_system_prompt
        prompt = _build_system_prompt({"genre": "sci-fi"})
        assert "sci-fi" in prompt

    def test_characters_included(self):
        from api.branch_routes import _build_system_prompt
        ctx = {"characters": [{"name": "Aria", "role": "hero", "personality": "brave"}]}
        prompt = _build_system_prompt(ctx)
        assert "Aria" in prompt
        assert "hero" in prompt

    def test_node_states_injected_into_characters(self):
        from api.branch_routes import _build_system_prompt
        ctx = {"characters": [{"name": "Aria", "role": "hero", "personality": "brave"}]}
        states = {"Aria": {"mood": "furious", "arc_position": "climax"}}
        prompt = _build_system_prompt(ctx, states)
        assert "furious" in prompt
        assert "climax" in prompt

    def test_world_and_conflict_included(self):
        from api.branch_routes import _build_system_prompt
        ctx = {"world_summary": "Dark forest realm", "conflict_summary": "ancient war"}
        prompt = _build_system_prompt(ctx)
        assert "Dark forest realm" in prompt
        assert "ancient war" in prompt
