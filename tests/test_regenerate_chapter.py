"""Tests for selective chapter regeneration feature (Phase 1)."""

import json
import pytest
import pytest_asyncio
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from models.schemas import (
    StoryDraft, Character, WorldSetting, ChapterOutline, Chapter,
    CharacterState, PlotEvent, StoryContext, PipelineOutput,
)
from pipeline.layer1_story.story_continuation import regenerate_chapter_impl


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
            Character(name="Villain", role="antagonist", personality="cunning", motivation="domination"),
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
# Unit Tests: regenerate_chapter_impl
# ══════════════════════════════════════════════════════════════════════════════

class TestRegenerateChapterImpl:
    """Unit tests for regenerate_chapter_impl function."""

    def test_invalid_chapter_number_raises(self):
        """Chapter number beyond outline count should raise ValueError."""
        gen = _make_generator()
        draft = _make_draft(num_chapters=3)

        with pytest.raises(ValueError, match="No outline for chapter"):
            regenerate_chapter_impl(gen, draft, chapter_number=10)

    @patch("pipeline.layer1_story.story_continuation.process_chapter_post_write")
    def test_regenerates_specified_chapter(self, mock_post_write):
        """Should replace the target chapter content."""
        gen = _make_generator()
        draft = _make_draft(num_chapters=3)

        new_chapter = Chapter(
            chapter_number=2, title="Chapter 2", content="New regenerated content", word_count=1500
        )
        gen._write_chapter_with_long_context.return_value = new_chapter
        mock_post_write.return_value = (new_chapter, "summary", [], [])

        result = regenerate_chapter_impl(gen, draft, chapter_number=2, word_count=1500)

        assert result.chapters[1].content == "New regenerated content"
        assert result.chapters[1].word_count == 1500

    @patch("pipeline.layer1_story.story_continuation.process_chapter_post_write")
    def test_preserves_other_chapters(self, mock_post_write):
        """Regeneration should not affect other chapters."""
        gen = _make_generator()
        draft = _make_draft(num_chapters=3)
        original_ch1 = draft.chapters[0].content
        original_ch3 = draft.chapters[2].content

        new_chapter = Chapter(
            chapter_number=2, title="Chapter 2", content="New content", word_count=1000
        )
        gen._write_chapter_with_long_context.return_value = new_chapter
        mock_post_write.return_value = (new_chapter, "summary", [], [])

        result = regenerate_chapter_impl(gen, draft, chapter_number=2)

        assert result.chapters[0].content == original_ch1
        assert result.chapters[2].content == original_ch3

    @patch("pipeline.layer1_story.story_continuation.process_chapter_post_write")
    def test_context_limited_to_preceding_chapters(self, mock_post_write):
        """rebuild_context should be called; context limited to chapters before target."""
        gen = _make_generator()
        draft = _make_draft(num_chapters=5)

        new_chapter = Chapter(chapter_number=3, title="Ch3", content="new", word_count=1000)
        gen._write_chapter_with_long_context.return_value = new_chapter
        mock_post_write.return_value = (new_chapter, "s", [], [])

        regenerate_chapter_impl(gen, draft, chapter_number=3)

        # Verify rebuild_context was called
        gen.rebuild_context.assert_called_once_with(draft)
        # Verify _write_chapter_with_long_context was called
        gen._write_chapter_with_long_context.assert_called_once()

    @patch("pipeline.layer1_story.story_continuation.process_chapter_post_write")
    def test_stream_callback_used_when_provided(self, mock_post_write):
        """Should use write_chapter_stream when stream_callback provided."""
        gen = _make_generator()
        draft = _make_draft(num_chapters=3)
        stream_cb = MagicMock()

        new_chapter = Chapter(chapter_number=2, title="Ch2", content="streamed", word_count=1000)
        gen.write_chapter_stream.return_value = new_chapter
        mock_post_write.return_value = (new_chapter, "s", [], [])

        regenerate_chapter_impl(gen, draft, chapter_number=2, stream_callback=stream_cb)

        gen.write_chapter_stream.assert_called_once()
        gen._write_chapter_with_long_context.assert_not_called()

    @patch("pipeline.layer1_story.story_continuation.process_chapter_post_write")
    def test_progress_callback_invoked(self, mock_post_write):
        """Progress callback should receive status messages."""
        gen = _make_generator()
        draft = _make_draft(num_chapters=3)
        progress_msgs = []

        new_chapter = Chapter(chapter_number=2, title="Ch2", content="new", word_count=1000)
        gen._write_chapter_with_long_context.return_value = new_chapter
        mock_post_write.return_value = (new_chapter, "s", [], [])

        regenerate_chapter_impl(gen, draft, chapter_number=2, progress_callback=progress_msgs.append)

        assert any("Regenerating chapter 2" in msg for msg in progress_msgs)
        assert any("regenerated successfully" in msg for msg in progress_msgs)


# ══════════════════════════════════════════════════════════════════════════════
# Unit Tests: StoryContinuation.regenerate_chapter
# ══════════════════════════════════════════════════════════════════════════════

class TestStoryContinuationRegenerateChapter:
    """Tests for StoryContinuation.regenerate_chapter method."""

    def test_raises_if_no_draft_loaded(self):
        """Should raise ValueError if no story draft loaded."""
        from pipeline.orchestrator_continuation import StoryContinuation

        output = PipelineOutput()
        cont = StoryContinuation(output, MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock())

        with pytest.raises(ValueError, match="No story draft loaded"):
            cont.regenerate_chapter(chapter_number=1)

    def test_raises_if_chapter_out_of_range(self):
        """Should raise for chapter_number < 1 or > len(chapters)."""
        from pipeline.orchestrator_continuation import StoryContinuation

        output = PipelineOutput(story_draft=_make_draft(num_chapters=3))
        cont = StoryContinuation(output, MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock())

        with pytest.raises(ValueError, match="Invalid chapter_number"):
            cont.regenerate_chapter(chapter_number=0)

        with pytest.raises(ValueError, match="Invalid chapter_number"):
            cont.regenerate_chapter(chapter_number=5)

    @patch("pipeline.layer1_story.story_continuation.regenerate_chapter_impl")
    def test_calls_impl_and_saves_checkpoint(self, mock_impl):
        """Should call regenerate_chapter_impl and save checkpoint."""
        from pipeline.orchestrator_continuation import StoryContinuation

        draft = _make_draft(num_chapters=3)
        output = PipelineOutput(story_draft=draft)
        checkpoint_mgr = MagicMock()

        cont = StoryContinuation(output, MagicMock(), MagicMock(), MagicMock(), MagicMock(), checkpoint_mgr)
        mock_impl.return_value = draft

        cont.regenerate_chapter(chapter_number=2, word_count=1500)

        mock_impl.assert_called_once()
        checkpoint_mgr.save.assert_called_once_with(1)

    @patch("pipeline.layer1_story.story_continuation.regenerate_chapter_impl")
    def test_invalidates_enhanced_story(self, mock_impl):
        """Should set enhanced_story to None after regeneration."""
        from pipeline.orchestrator_continuation import StoryContinuation
        from models.schemas import EnhancedStory

        draft = _make_draft(num_chapters=3)
        enhanced = EnhancedStory(title="Test", genre="fantasy", chapters=[])
        output = PipelineOutput(story_draft=draft, enhanced_story=enhanced)

        cont = StoryContinuation(output, MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock())
        mock_impl.return_value = draft

        cont.regenerate_chapter(chapter_number=2)

        assert cont.output.enhanced_story is None


# ══════════════════════════════════════════════════════════════════════════════
# API Tests: POST /pipeline/regenerate-chapter
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


def _parse_sse_events(body: str) -> list[dict]:
    """Parse SSE text into list of event dicts."""
    events = []
    for line in body.strip().split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


class TestRegenerateChapterAPI:
    """API endpoint tests for /pipeline/regenerate-chapter."""

    @pytest.mark.asyncio
    async def test_checkpoint_not_found_returns_error(self, client):
        """Non-existent checkpoint should return SSE error."""
        resp = await client.post(
            "/api/pipeline/regenerate-chapter",
            json={"checkpoint": "nonexistent.json", "chapter_number": 1},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        events = _parse_sse_events(resp.text)
        assert events[0]["type"] == "error"
        assert "not found" in events[0]["data"].lower()

    @pytest.mark.asyncio
    async def test_sse_headers_correct(self, client):
        """Should return correct SSE headers."""
        resp = await client.post(
            "/api/pipeline/regenerate-chapter",
            json={"checkpoint": "test.json", "chapter_number": 1},
        )
        assert "text/event-stream" in resp.headers["content-type"]
        assert resp.headers.get("cache-control") == "no-cache"

    @pytest.mark.asyncio
    async def test_validates_chapter_number_min(self, client):
        """chapter_number must be >= 1."""
        resp = await client.post(
            "/api/pipeline/regenerate-chapter",
            json={"checkpoint": "test.json", "chapter_number": 0},
        )
        assert resp.status_code == 422  # Pydantic validation error

    @pytest.mark.asyncio
    async def test_validates_word_count_range(self, client):
        """word_count must be between 100 and 20000."""
        resp = await client.post(
            "/api/pipeline/regenerate-chapter",
            json={"checkpoint": "test.json", "chapter_number": 1, "word_count": 50},
        )
        assert resp.status_code == 422

        resp = await client.post(
            "/api/pipeline/regenerate-chapter",
            json={"checkpoint": "test.json", "chapter_number": 1, "word_count": 25000},
        )
        assert resp.status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
# Edge Case Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestRegenerateEdgeCases:
    """Edge case and boundary tests."""

    @patch("pipeline.layer1_story.story_continuation.process_chapter_post_write")
    def test_regenerate_first_chapter(self, mock_post_write):
        """Regenerating chapter 1 should work with empty context."""
        gen = _make_generator()
        draft = _make_draft(num_chapters=3)

        new_chapter = Chapter(chapter_number=1, title="Ch1", content="new first", word_count=1000)
        gen._write_chapter_with_long_context.return_value = new_chapter
        mock_post_write.return_value = (new_chapter, "s", [], [])

        result = regenerate_chapter_impl(gen, draft, chapter_number=1)

        assert result.chapters[0].content == "new first"

    @patch("pipeline.layer1_story.story_continuation.process_chapter_post_write")
    def test_regenerate_last_chapter(self, mock_post_write):
        """Regenerating last chapter should include all preceding context."""
        gen = _make_generator()
        draft = _make_draft(num_chapters=3)

        new_chapter = Chapter(chapter_number=3, title="Ch3", content="new last", word_count=1000)
        gen._write_chapter_with_long_context.return_value = new_chapter
        mock_post_write.return_value = (new_chapter, "s", [], [])

        result = regenerate_chapter_impl(gen, draft, chapter_number=3)

        assert result.chapters[2].content == "new last"
        # Verify _write_chapter_with_long_context was called
        gen._write_chapter_with_long_context.assert_called_once()

    @patch("pipeline.layer1_story.story_continuation.process_chapter_post_write")
    def test_custom_style_passed_to_writer(self, mock_post_write):
        """Custom style should override default."""
        gen = _make_generator()
        draft = _make_draft(num_chapters=3)

        new_chapter = Chapter(chapter_number=2, title="Ch2", content="styled", word_count=1000)
        gen._write_chapter_with_long_context.return_value = new_chapter
        mock_post_write.return_value = (new_chapter, "s", [], [])

        regenerate_chapter_impl(gen, draft, chapter_number=2, style="noir")

        call_args = gen._write_chapter_with_long_context.call_args
        effective_style = call_args[0][2]  # 3rd positional arg is style
        assert effective_style == "noir"
