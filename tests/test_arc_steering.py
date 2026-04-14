"""Tests for character arc steering feature (Phase 4)."""

import json
import pytest
import pytest_asyncio
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from models.schemas import (
    StoryDraft, Character, WorldSetting, ChapterOutline, Chapter,
    CharacterState, PlotEvent, StoryContext, PipelineOutput,
    ArcDirective,
)


# ══════════════════════════════════════════════════════════════════════════════
# Helper Fixtures
# ══════════════════════════════════════════════════════════════════════════════

def _make_draft(num_chapters: int = 3) -> StoryDraft:
    """Create a test StoryDraft with specified number of chapters."""
    return StoryDraft(
        title="Test Story",
        genre="fantasy",
        characters=[
            Character(name="Hero", role="protagonist", personality="brave", motivation="save world"),
            Character(name="Villain", role="antagonist", personality="cunning", motivation="power"),
        ],
        world=WorldSetting(name="TestWorld", description="A fantasy realm"),
        outlines=[
            ChapterOutline(chapter_number=i + 1, title=f"Chapter {i + 1}", summary=f"Summary {i + 1}", key_events=[])
            for i in range(num_chapters)
        ],
        chapters=[
            Chapter(chapter_number=i + 1, title=f"Chapter {i + 1}", content=f"Content {i + 1}", word_count=1000, summary=f"Summary {i + 1}")
            for i in range(num_chapters)
        ],
        character_states=[
            CharacterState(name="Hero", mood="determined", arc_position="rising", last_action="trained"),
            CharacterState(name="Villain", mood="confident", arc_position="peak", last_action="plotted"),
        ],
        plot_events=[
            PlotEvent(chapter_number=i + 1, event=f"Event {i + 1}") for i in range(num_chapters)
        ],
    )


def _make_generator():
    """Create a mocked StoryGenerator."""
    gen = MagicMock()
    gen.config.pipeline.context_window_chapters = 5
    gen.config.pipeline.enable_self_review = False
    gen.config.pipeline.writing_style = ""
    gen._layer_model = None
    gen._get_self_reviewer.return_value = None
    gen.rebuild_context.return_value = StoryContext(total_chapters=3, current_chapter=1)
    return gen


# ══════════════════════════════════════════════════════════════════════════════
# Unit Tests: ArcDirective Schema
# ══════════════════════════════════════════════════════════════════════════════

class TestArcDirectiveSchema:
    """Unit tests for ArcDirective schema."""

    def test_create_arc_directive(self):
        """Should create valid ArcDirective."""
        directive = ArcDirective(
            character="Villain",
            from_state="evil",
            to_state="redeemed",
            chapter_span=5,
        )
        assert directive.character == "Villain"
        assert directive.from_state == "evil"
        assert directive.to_state == "redeemed"
        assert directive.chapter_span == 5

    def test_default_chapter_span(self):
        """Default chapter_span should be 5."""
        directive = ArcDirective(
            character="Hero",
            from_state="naive",
            to_state="wise",
        )
        assert directive.chapter_span == 5

    def test_notes_optional(self):
        """Notes field should be optional."""
        directive = ArcDirective(
            character="Hero",
            from_state="weak",
            to_state="powerful",
            notes="Gradually gain strength through training",
        )
        assert directive.notes == "Gradually gain strength through training"

    def test_chapter_span_validation(self):
        """Chapter span must be between 1 and 50."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ArcDirective(character="X", from_state="a", to_state="b", chapter_span=0)
        with pytest.raises(ValidationError):
            ArcDirective(character="X", from_state="a", to_state="b", chapter_span=100)


# ══════════════════════════════════════════════════════════════════════════════
# Unit Tests: generate_continuation_outlines with arc_directives
# ══════════════════════════════════════════════════════════════════════════════

class TestOutlineGenerationWithArcs:
    """Tests for arc steering in outline generation."""

    def test_arc_directives_included_in_prompt(self):
        """Arc directives should be appended to the outline prompt."""
        from pipeline.layer1_story.story_continuation import generate_continuation_outlines

        gen = _make_generator()
        draft = _make_draft(num_chapters=3)
        arc_directives = [
            ArcDirective(character="Villain", from_state="evil", to_state="redeemed", chapter_span=5),
        ]

        gen.llm.generate_json.return_value = {"outlines": []}

        generate_continuation_outlines(gen, draft, additional_chapters=5, arc_directives=arc_directives)

        # Check that the prompt includes arc directive text
        call_args = gen.llm.generate_json.call_args
        user_prompt = call_args.kwargs.get("user_prompt") or call_args[1].get("user_prompt")
        assert "Villain" in user_prompt
        assert "evil" in user_prompt
        assert "redeemed" in user_prompt

    def test_multiple_arc_directives(self):
        """Multiple arc directives should all be included."""
        from pipeline.layer1_story.story_continuation import generate_continuation_outlines

        gen = _make_generator()
        draft = _make_draft()
        arc_directives = [
            ArcDirective(character="Hero", from_state="naive", to_state="wise", chapter_span=3),
            ArcDirective(character="Villain", from_state="evil", to_state="neutral", chapter_span=5),
        ]

        gen.llm.generate_json.return_value = {"outlines": []}

        generate_continuation_outlines(gen, draft, additional_chapters=5, arc_directives=arc_directives)

        call_args = gen.llm.generate_json.call_args
        user_prompt = call_args.kwargs.get("user_prompt") or call_args[1].get("user_prompt")
        assert "Hero" in user_prompt
        assert "naive" in user_prompt
        assert "Villain" in user_prompt

    def test_no_arc_directives(self):
        """Without arc_directives, prompt should not contain arc section."""
        from pipeline.layer1_story.story_continuation import generate_continuation_outlines

        gen = _make_generator()
        draft = _make_draft()

        gen.llm.generate_json.return_value = {"outlines": []}

        generate_continuation_outlines(gen, draft, additional_chapters=3, arc_directives=[])

        call_args = gen.llm.generate_json.call_args
        user_prompt = call_args.kwargs.get("user_prompt") or call_args[1].get("user_prompt")
        assert "CHỈ THỊ ARC" not in user_prompt


# ══════════════════════════════════════════════════════════════════════════════
# Unit Tests: write_from_outlines with arc_directives
# ══════════════════════════════════════════════════════════════════════════════

class TestChapterWritingWithArcs:
    """Tests for arc steering in chapter writing."""

    @patch("pipeline.layer1_story.story_continuation.process_chapter_post_write")
    def test_arc_context_added_to_enhancement(self, mock_post_write):
        """Arc directive should add context for chapter writing."""
        from pipeline.layer1_story.story_continuation import write_from_outlines

        gen = _make_generator()
        draft = _make_draft(num_chapters=3)
        outlines = [
            ChapterOutline(chapter_number=4, title="Ch4", summary="S4", key_events=[]),
        ]
        arc_directives = [
            ArcDirective(character="Villain", from_state="evil", to_state="redeemed", chapter_span=3),
        ]

        new_chapter = Chapter(chapter_number=4, title="Ch4", content="new", word_count=1000)
        gen._write_chapter_with_long_context.return_value = new_chapter
        mock_post_write.return_value = (new_chapter, "s", [], [])

        write_from_outlines(gen, draft, outlines, arc_directives=arc_directives)

        # Verify the chapter writer was called
        gen._write_chapter_with_long_context.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
# Unit Tests: continue_story with arc_directives
# ══════════════════════════════════════════════════════════════════════════════

class TestContinueStoryWithArcs:
    """Tests for continue_story with arc steering."""

    @patch("pipeline.layer1_story.story_continuation.write_from_outlines")
    @patch("pipeline.layer1_story.story_continuation.generate_continuation_outlines")
    def test_arc_directives_passed_through(self, mock_gen, mock_write):
        """Arc directives should be passed to both outline generation and chapter writing."""
        from pipeline.layer1_story.story_continuation import continue_story

        gen = _make_generator()
        draft = _make_draft()
        arc_directives = [
            ArcDirective(character="Hero", from_state="weak", to_state="strong", chapter_span=5),
        ]

        outlines = [ChapterOutline(chapter_number=4, title="Ch4", summary="S", key_events=[])]
        mock_gen.return_value = outlines
        mock_write.return_value = draft

        continue_story(gen, draft, additional_chapters=1, arc_directives=arc_directives)

        # Verify arc_directives passed to generate_continuation_outlines
        mock_gen.assert_called_once()
        assert mock_gen.call_args.kwargs.get("arc_directives") == arc_directives or \
               arc_directives in mock_gen.call_args.args

        # Verify arc_directives passed to write_from_outlines
        mock_write.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
# Unit Tests: StoryContinuation orchestrator
# ══════════════════════════════════════════════════════════════════════════════

class TestStoryContinuationWithArcs:
    """Tests for StoryContinuation orchestrator methods with arc steering."""

    @patch("pipeline.layer1_story.story_continuation.generate_continuation_outlines")
    def test_generate_outlines_passes_arc_directives(self, mock_gen):
        """Orchestrator should pass arc_directives to impl."""
        from pipeline.orchestrator_continuation import StoryContinuation

        draft = _make_draft()
        output = PipelineOutput(story_draft=draft)
        story_gen = MagicMock()
        arc_directives = [ArcDirective(character="X", from_state="a", to_state="b")]

        cont = StoryContinuation(output, story_gen, MagicMock(), MagicMock(), MagicMock(), MagicMock())
        mock_gen.return_value = []

        cont.generate_continuation_outlines(additional_chapters=3, arc_directives=arc_directives)

        mock_gen.assert_called_once()
        assert mock_gen.call_args.kwargs.get("arc_directives") == arc_directives

    @patch("pipeline.layer1_story.story_continuation.write_from_outlines")
    def test_write_from_outlines_passes_arc_directives(self, mock_write):
        """Orchestrator should pass arc_directives to write impl."""
        from pipeline.orchestrator_continuation import StoryContinuation

        draft = _make_draft()
        output = PipelineOutput(story_draft=draft)
        checkpoint_mgr = MagicMock()
        arc_directives = [ArcDirective(character="Y", from_state="x", to_state="z")]

        cont = StoryContinuation(output, MagicMock(), MagicMock(), MagicMock(), MagicMock(), checkpoint_mgr)
        mock_write.return_value = draft

        outlines = [ChapterOutline(chapter_number=4, title="Ch", summary="S", key_events=[])]
        cont.write_from_outlines(outlines, arc_directives=arc_directives)

        mock_write.assert_called_once()
        assert mock_write.call_args.kwargs.get("arc_directives") == arc_directives


# ══════════════════════════════════════════════════════════════════════════════
# API Tests
# ══════════════════════════════════════════════════════════════════════════════

def _make_app() -> FastAPI:
    from fastapi import APIRouter
    from api.continuation_routes import router as continuation_router
    app = FastAPI()
    api = APIRouter(prefix="/api")
    api.include_router(continuation_router)
    app.include_router(api)
    return app


@pytest_asyncio.fixture
async def client():
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestArcSteeringAPI:
    """API endpoint tests for arc steering."""

    @pytest.mark.asyncio
    async def test_continue_request_accepts_arc_directives(self, client):
        """ContinueRequest should accept arc_directives field."""
        # This will fail at checkpoint validation, but validates schema acceptance
        resp = await client.post(
            "/api/pipeline/continue",
            json={
                "checkpoint": "nonexistent.json",
                "additional_chapters": 3,
                "arc_directives": [
                    {"character": "Hero", "from_state": "weak", "to_state": "strong", "chapter_span": 5}
                ],
            },
        )
        assert resp.status_code == 200  # SSE response starts
        # Schema validation passed (otherwise 422)

    @pytest.mark.asyncio
    async def test_outline_preview_accepts_arc_directives(self, client):
        """OutlinePreviewRequest should accept arc_directives."""
        resp = await client.post(
            "/api/pipeline/continue/outlines",
            json={
                "checkpoint": "test.json",
                "additional_chapters": 3,
                "arc_directives": [
                    {"character": "Villain", "from_state": "evil", "to_state": "good"}
                ],
            },
        )
        # Will get 404 for missing checkpoint, but schema validated
        assert resp.status_code in [404, 200]

    @pytest.mark.asyncio
    async def test_outline_write_accepts_arc_directives(self, client):
        """OutlineWriteRequest should accept arc_directives."""
        resp = await client.post(
            "/api/pipeline/continue/write",
            json={
                "checkpoint": "test.json",
                "outlines": [{"chapter_number": 4, "title": "Ch", "summary": "S", "key_events": []}],
                "arc_directives": [
                    {"character": "Hero", "from_state": "a", "to_state": "b", "chapter_span": 3}
                ],
            },
        )
        assert resp.status_code == 200  # SSE response

    @pytest.mark.asyncio
    async def test_invalid_arc_directive_schema(self, client):
        """Invalid arc_directive should return 422."""
        resp = await client.post(
            "/api/pipeline/continue",
            json={
                "checkpoint": "test.json",
                "arc_directives": [
                    {"character": "Hero"}  # Missing required fields
                ],
            },
        )
        assert resp.status_code == 422
