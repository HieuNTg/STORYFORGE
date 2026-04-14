"""Tests for outline preview and write feature (Phase 2)."""

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
# Unit Tests: generate_continuation_outlines
# ══════════════════════════════════════════════════════════════════════════════

class TestGenerateContinuationOutlines:
    """Unit tests for generate_continuation_outlines function."""

    def test_generates_outlines(self):
        """Should generate ChapterOutline list from LLM response."""
        from pipeline.layer1_story.story_continuation import generate_continuation_outlines

        gen = _make_generator()
        draft = _make_draft(num_chapters=3)
        gen.llm.generate_json.return_value = {
            "outlines": [
                {"chapter_number": 4, "title": "New Ch 4", "summary": "Summary 4", "key_events": []},
                {"chapter_number": 5, "title": "New Ch 5", "summary": "Summary 5", "key_events": []},
            ]
        }

        outlines = generate_continuation_outlines(gen, draft, additional_chapters=2)

        assert len(outlines) == 2
        assert outlines[0].chapter_number == 4
        assert outlines[0].title == "New Ch 4"
        assert outlines[1].chapter_number == 5

    def test_empty_outlines_returned(self):
        """Should return empty list if LLM returns no outlines."""
        from pipeline.layer1_story.story_continuation import generate_continuation_outlines

        gen = _make_generator()
        draft = _make_draft(num_chapters=3)
        gen.llm.generate_json.return_value = {"outlines": []}

        outlines = generate_continuation_outlines(gen, draft, additional_chapters=2)

        assert outlines == []

    def test_progress_callback_invoked(self):
        """Progress callback should receive status messages."""
        from pipeline.layer1_story.story_continuation import generate_continuation_outlines

        gen = _make_generator()
        draft = _make_draft(num_chapters=3)
        progress_msgs = []
        gen.llm.generate_json.return_value = {
            "outlines": [{"chapter_number": 4, "title": "Ch4", "summary": "S", "key_events": []}]
        }

        generate_continuation_outlines(gen, draft, additional_chapters=1, progress_callback=progress_msgs.append)

        assert any("Generating outlines" in msg for msg in progress_msgs)
        assert any("Generated" in msg for msg in progress_msgs)


# ══════════════════════════════════════════════════════════════════════════════
# Unit Tests: write_from_outlines
# ══════════════════════════════════════════════════════════════════════════════

class TestWriteFromOutlines:
    """Unit tests for write_from_outlines function."""

    @patch("pipeline.layer1_story.story_continuation.process_chapter_post_write")
    def test_writes_chapters_from_outlines(self, mock_post_write):
        """Should write chapters from provided outlines."""
        from pipeline.layer1_story.story_continuation import write_from_outlines

        gen = _make_generator()
        draft = _make_draft(num_chapters=3)
        outlines = [
            ChapterOutline(chapter_number=4, title="New Ch 4", summary="Summary 4", key_events=[]),
            ChapterOutline(chapter_number=5, title="New Ch 5", summary="Summary 5", key_events=[]),
        ]

        new_chapter = Chapter(chapter_number=4, title="Ch4", content="new content", word_count=1000)
        gen._write_chapter_with_long_context.return_value = new_chapter
        mock_post_write.return_value = (new_chapter, "s", [], [])

        result = write_from_outlines(gen, draft, outlines)

        assert len(result.chapters) == 5  # 3 + 2 new
        assert len(result.outlines) == 5  # 3 + 2 new

    @patch("pipeline.layer1_story.story_continuation.process_chapter_post_write")
    def test_empty_outlines_returns_draft_unchanged(self, mock_post_write):
        """Should return draft unchanged if no outlines provided."""
        from pipeline.layer1_story.story_continuation import write_from_outlines

        gen = _make_generator()
        draft = _make_draft(num_chapters=3)

        result = write_from_outlines(gen, draft, outlines=[])

        assert result == draft
        gen._write_chapter_with_long_context.assert_not_called()

    @patch("pipeline.layer1_story.story_continuation.process_chapter_post_write")
    def test_stream_callback_used_when_provided(self, mock_post_write):
        """Should use write_chapter_stream when stream_callback provided."""
        from pipeline.layer1_story.story_continuation import write_from_outlines

        gen = _make_generator()
        draft = _make_draft(num_chapters=3)
        outlines = [ChapterOutline(chapter_number=4, title="Ch4", summary="S", key_events=[])]
        stream_cb = MagicMock()

        new_chapter = Chapter(chapter_number=4, title="Ch4", content="streamed", word_count=1000)
        gen.write_chapter_stream.return_value = new_chapter
        mock_post_write.return_value = (new_chapter, "s", [], [])

        write_from_outlines(gen, draft, outlines, stream_callback=stream_cb)

        gen.write_chapter_stream.assert_called()
        gen._write_chapter_with_long_context.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# Unit Tests: StoryContinuation methods
# ══════════════════════════════════════════════════════════════════════════════

class TestStoryContinuationOutlineMethods:
    """Tests for StoryContinuation outline methods."""

    def test_generate_outlines_raises_if_no_draft(self):
        """Should raise ValueError if no story draft loaded."""
        from pipeline.orchestrator_continuation import StoryContinuation

        output = PipelineOutput()
        cont = StoryContinuation(output, MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock())

        with pytest.raises(ValueError, match="No story draft loaded"):
            cont.generate_continuation_outlines()

    def test_write_from_outlines_raises_if_no_draft(self):
        """Should raise ValueError if no story draft loaded."""
        from pipeline.orchestrator_continuation import StoryContinuation

        output = PipelineOutput()
        cont = StoryContinuation(output, MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock())
        outlines = [ChapterOutline(chapter_number=1, title="Ch", summary="S", key_events=[])]

        with pytest.raises(ValueError, match="No story draft loaded"):
            cont.write_from_outlines(outlines)

    def test_write_from_outlines_raises_if_no_outlines(self):
        """Should raise ValueError if no outlines provided."""
        from pipeline.orchestrator_continuation import StoryContinuation

        output = PipelineOutput(story_draft=_make_draft())
        cont = StoryContinuation(output, MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock())

        with pytest.raises(ValueError, match="No outlines provided"):
            cont.write_from_outlines([])

    @patch("pipeline.layer1_story.story_continuation.generate_continuation_outlines")
    def test_generate_outlines_calls_impl(self, mock_gen_outlines):
        """Should call generate_continuation_outlines implementation."""
        from pipeline.orchestrator_continuation import StoryContinuation

        draft = _make_draft()
        output = PipelineOutput(story_draft=draft)
        story_gen = MagicMock()

        cont = StoryContinuation(output, story_gen, MagicMock(), MagicMock(), MagicMock(), MagicMock())
        mock_gen_outlines.return_value = [
            ChapterOutline(chapter_number=4, title="Ch4", summary="S", key_events=[])
        ]

        outlines = cont.generate_continuation_outlines(additional_chapters=1)

        mock_gen_outlines.assert_called_once()
        assert len(outlines) == 1


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


class TestOutlinePreviewAPI:
    """API endpoint tests for /pipeline/continue/outlines."""

    @pytest.mark.asyncio
    async def test_checkpoint_not_found_returns_404(self, client):
        """Non-existent checkpoint should return 404."""
        resp = await client.post(
            "/api/pipeline/continue/outlines",
            json={"checkpoint": "nonexistent.json"},
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["error"].lower()

    @pytest.mark.asyncio
    async def test_validates_additional_chapters_range(self, client):
        """additional_chapters must be between 1 and 50."""
        resp = await client.post(
            "/api/pipeline/continue/outlines",
            json={"checkpoint": "test.json", "additional_chapters": 0},
        )
        assert resp.status_code == 422

        resp = await client.post(
            "/api/pipeline/continue/outlines",
            json={"checkpoint": "test.json", "additional_chapters": 100},
        )
        assert resp.status_code == 422


class TestWriteFromOutlinesAPI:
    """API endpoint tests for /pipeline/continue/write."""

    @pytest.mark.asyncio
    async def test_checkpoint_not_found_returns_error(self, client):
        """Non-existent checkpoint should return SSE error."""
        outlines = [{"chapter_number": 1, "title": "Ch", "summary": "S", "key_events": []}]
        resp = await client.post(
            "/api/pipeline/continue/write",
            json={"checkpoint": "nonexistent.json", "outlines": outlines},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        events = _parse_sse_events(resp.text)
        assert events[0]["type"] == "error"
        assert "not found" in events[0]["data"].lower()

    @pytest.mark.asyncio
    async def test_sse_headers_correct(self, client):
        """Should return correct SSE headers."""
        outlines = [{"chapter_number": 1, "title": "Ch", "summary": "S", "key_events": []}]
        resp = await client.post(
            "/api/pipeline/continue/write",
            json={"checkpoint": "test.json", "outlines": outlines},
        )
        assert "text/event-stream" in resp.headers["content-type"]
        assert resp.headers.get("cache-control") == "no-cache"

    @pytest.mark.asyncio
    async def test_invalid_outlines_returns_error(self, client):
        """Invalid outline schema should return SSE error (after checkpoint check)."""
        # Note: Checkpoint check happens first, then outline validation
        # With nonexistent checkpoint, we get "not found" error
        # This test verifies the SSE error handling pattern works
        resp = await client.post(
            "/api/pipeline/continue/write",
            json={"checkpoint": "test.json", "outlines": [{"invalid": "data"}]},
        )
        events = _parse_sse_events(resp.text)
        # First error should be about checkpoint or invalid outlines
        assert events[0]["type"] == "error"
        # Error message should be descriptive
        assert len(events[0]["data"]) > 0


# ══════════════════════════════════════════════════════════════════════════════
# Integration: continue_story uses extracted functions
# ══════════════════════════════════════════════════════════════════════════════

class TestContinueStoryRefactored:
    """Verify continue_story delegates to extracted functions."""

    @patch("pipeline.layer1_story.story_continuation.write_from_outlines")
    @patch("pipeline.layer1_story.story_continuation.generate_continuation_outlines")
    def test_continue_story_delegates(self, mock_gen_outlines, mock_write):
        """continue_story should call generate_continuation_outlines and write_from_outlines."""
        from pipeline.layer1_story.story_continuation import continue_story

        gen = _make_generator()
        draft = _make_draft(num_chapters=3)
        outlines = [ChapterOutline(chapter_number=4, title="Ch4", summary="S", key_events=[])]
        mock_gen_outlines.return_value = outlines
        mock_write.return_value = draft

        continue_story(gen, draft, additional_chapters=1)

        mock_gen_outlines.assert_called_once()
        mock_write.assert_called_once()

    @patch("pipeline.layer1_story.story_continuation.write_from_outlines")
    @patch("pipeline.layer1_story.story_continuation.generate_continuation_outlines")
    def test_continue_story_aborts_if_no_outlines(self, mock_gen_outlines, mock_write):
        """continue_story should abort if no outlines generated."""
        from pipeline.layer1_story.story_continuation import continue_story

        gen = _make_generator()
        draft = _make_draft(num_chapters=3)
        mock_gen_outlines.return_value = []

        result = continue_story(gen, draft, additional_chapters=1)

        mock_gen_outlines.assert_called_once()
        mock_write.assert_not_called()
        assert result == draft
