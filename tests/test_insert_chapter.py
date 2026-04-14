"""Tests for chapter insertion feature (Phase 3)."""

import json
import pytest
import pytest_asyncio
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from models.schemas import (
    StoryDraft, Character, WorldSetting, ChapterOutline, Chapter,
    CharacterState, PlotEvent, StoryContext, PipelineOutput,
    ForeshadowingEntry, PlotThread,
)


# ══════════════════════════════════════════════════════════════════════════════
# Helper Fixtures
# ══════════════════════════════════════════════════════════════════════════════

def _make_draft(num_chapters: int = 5) -> StoryDraft:
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
    gen.rebuild_context.return_value = StoryContext(total_chapters=5, current_chapter=1)
    return gen


# ══════════════════════════════════════════════════════════════════════════════
# Unit Tests: renumber_chapters
# ══════════════════════════════════════════════════════════════════════════════

class TestRenumberChapters:
    """Unit tests for renumber_chapters utility."""

    def test_renumbers_chapters(self):
        """Chapters at and after position should be incremented."""
        from pipeline.layer1_story.story_continuation import renumber_chapters

        draft = _make_draft(num_chapters=5)
        renumber_chapters(draft, from_position=3, delta=1)

        assert draft.chapters[0].chapter_number == 1
        assert draft.chapters[1].chapter_number == 2
        assert draft.chapters[2].chapter_number == 4  # Was 3, now 4
        assert draft.chapters[3].chapter_number == 5  # Was 4, now 5
        assert draft.chapters[4].chapter_number == 6  # Was 5, now 6

    def test_renumbers_outlines(self):
        """Outlines should also be renumbered."""
        from pipeline.layer1_story.story_continuation import renumber_chapters

        draft = _make_draft(num_chapters=5)
        renumber_chapters(draft, from_position=2, delta=1)

        assert draft.outlines[0].chapter_number == 1
        assert draft.outlines[1].chapter_number == 3  # Was 2
        assert draft.outlines[2].chapter_number == 4  # Was 3

    def test_renumbers_plot_events(self):
        """Plot events should reference updated chapter numbers."""
        from pipeline.layer1_story.story_continuation import renumber_chapters

        draft = _make_draft(num_chapters=5)
        renumber_chapters(draft, from_position=3, delta=1)

        assert draft.plot_events[0].chapter_number == 1
        assert draft.plot_events[1].chapter_number == 2
        assert draft.plot_events[2].chapter_number == 4  # Was 3

    def test_renumbers_foreshadowing(self):
        """Foreshadowing plant/payoff chapters should be updated."""
        from pipeline.layer1_story.story_continuation import renumber_chapters

        draft = _make_draft(num_chapters=5)
        draft.foreshadowing_plan = [
            ForeshadowingEntry(hint="omen", plant_chapter=2, payoff_chapter=4),
        ]

        renumber_chapters(draft, from_position=3, delta=1)

        assert draft.foreshadowing_plan[0].plant_chapter == 2  # Before insert point
        assert draft.foreshadowing_plan[0].payoff_chapter == 5  # Was 4, now 5

    def test_renumbers_threads(self):
        """Thread chapter references should be updated."""
        from pipeline.layer1_story.story_continuation import renumber_chapters

        draft = _make_draft(num_chapters=5)
        draft.open_threads = [
            PlotThread(thread_id="t1", description="A mystery", status="open", planted_chapter=1, last_mentioned_chapter=3),
        ]

        renumber_chapters(draft, from_position=2, delta=1)

        assert draft.open_threads[0].planted_chapter == 1
        assert draft.open_threads[0].last_mentioned_chapter == 4  # Was 3


# ══════════════════════════════════════════════════════════════════════════════
# Unit Tests: insert_chapter_impl
# ══════════════════════════════════════════════════════════════════════════════

class TestInsertChapterImpl:
    """Unit tests for insert_chapter_impl function."""

    def test_invalid_position_raises(self):
        """insert_after beyond chapter count should raise ValueError."""
        from pipeline.layer1_story.story_continuation import insert_chapter_impl

        gen = _make_generator()
        draft = _make_draft(num_chapters=5)

        with pytest.raises(ValueError, match="Invalid insert_after"):
            insert_chapter_impl(gen, draft, insert_after=10)

    def test_negative_position_raises(self):
        """Negative insert_after should raise ValueError."""
        from pipeline.layer1_story.story_continuation import insert_chapter_impl

        gen = _make_generator()
        draft = _make_draft(num_chapters=5)

        with pytest.raises(ValueError, match="Invalid insert_after"):
            insert_chapter_impl(gen, draft, insert_after=-1)

    @patch("pipeline.layer1_story.story_continuation.process_chapter_post_write")
    def test_inserts_at_middle(self, mock_post_write):
        """Should insert chapter at correct position."""
        from pipeline.layer1_story.story_continuation import insert_chapter_impl

        gen = _make_generator()
        draft = _make_draft(num_chapters=5)
        gen.llm.generate_json.return_value = {
            "title": "Inserted Chapter",
            "summary": "A bridge chapter",
            "key_events": [],
        }
        new_chapter = Chapter(chapter_number=3, title="Inserted", content="new", word_count=1000)
        gen._write_chapter_with_long_context.return_value = new_chapter
        mock_post_write.return_value = (new_chapter, "s", [], [])

        result = insert_chapter_impl(gen, draft, insert_after=2)

        assert len(result.chapters) == 6
        # The inserted chapter should be at index 2 (chapter number 3)
        assert result.chapters[2].title == "Inserted"

    @patch("pipeline.layer1_story.story_continuation.process_chapter_post_write")
    def test_inserts_at_beginning(self, mock_post_write):
        """insert_after=0 should insert at the beginning."""
        from pipeline.layer1_story.story_continuation import insert_chapter_impl

        gen = _make_generator()
        draft = _make_draft(num_chapters=3)
        gen.llm.generate_json.return_value = {"title": "New First", "summary": "s", "key_events": []}
        new_chapter = Chapter(chapter_number=1, title="New First", content="new", word_count=1000)
        gen._write_chapter_with_long_context.return_value = new_chapter
        mock_post_write.return_value = (new_chapter, "s", [], [])

        result = insert_chapter_impl(gen, draft, insert_after=0)

        assert len(result.chapters) == 4
        assert result.chapters[0].title == "New First"

    @patch("pipeline.layer1_story.story_continuation.process_chapter_post_write")
    def test_progress_callback_invoked(self, mock_post_write):
        """Progress callback should receive status messages."""
        from pipeline.layer1_story.story_continuation import insert_chapter_impl

        gen = _make_generator()
        draft = _make_draft(num_chapters=3)
        progress_msgs = []
        gen.llm.generate_json.return_value = {"title": "Ch", "summary": "s", "key_events": []}
        new_chapter = Chapter(chapter_number=2, title="Ch", content="c", word_count=1000)
        gen._write_chapter_with_long_context.return_value = new_chapter
        mock_post_write.return_value = (new_chapter, "s", [], [])

        insert_chapter_impl(gen, draft, insert_after=1, progress_callback=progress_msgs.append)

        assert any("Inserting" in msg for msg in progress_msgs)
        assert any("inserted successfully" in msg for msg in progress_msgs)


# ══════════════════════════════════════════════════════════════════════════════
# Unit Tests: StoryContinuation.insert_chapter
# ══════════════════════════════════════════════════════════════════════════════

class TestStoryContinuationInsertChapter:
    """Tests for StoryContinuation.insert_chapter method."""

    def test_raises_if_no_draft(self):
        """Should raise ValueError if no story draft loaded."""
        from pipeline.orchestrator_continuation import StoryContinuation

        output = PipelineOutput()
        cont = StoryContinuation(output, MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock())

        with pytest.raises(ValueError, match="No story draft loaded"):
            cont.insert_chapter(insert_after=1)

    @patch("pipeline.layer1_story.story_continuation.insert_chapter_impl")
    def test_calls_impl_and_saves_checkpoint(self, mock_impl):
        """Should call insert_chapter_impl and save checkpoint."""
        from pipeline.orchestrator_continuation import StoryContinuation

        draft = _make_draft()
        output = PipelineOutput(story_draft=draft)
        checkpoint_mgr = MagicMock()

        cont = StoryContinuation(output, MagicMock(), MagicMock(), MagicMock(), MagicMock(), checkpoint_mgr)
        mock_impl.return_value = draft

        cont.insert_chapter(insert_after=2)

        mock_impl.assert_called_once()
        checkpoint_mgr.save.assert_called_once_with(1)

    @patch("pipeline.layer1_story.story_continuation.insert_chapter_impl")
    def test_invalidates_enhanced_story(self, mock_impl):
        """Should set enhanced_story to None after insertion."""
        from pipeline.orchestrator_continuation import StoryContinuation
        from models.schemas import EnhancedStory

        draft = _make_draft()
        enhanced = EnhancedStory(title="Test", genre="fantasy", chapters=[])
        output = PipelineOutput(story_draft=draft, enhanced_story=enhanced)

        cont = StoryContinuation(output, MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock())
        mock_impl.return_value = draft

        cont.insert_chapter(insert_after=2)

        assert cont.output.enhanced_story is None


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


class TestInsertChapterAPI:
    """API endpoint tests for /pipeline/insert-chapter."""

    @pytest.mark.asyncio
    async def test_checkpoint_not_found_returns_error(self, client):
        """Non-existent checkpoint should return SSE error."""
        resp = await client.post(
            "/api/pipeline/insert-chapter",
            json={"checkpoint": "nonexistent.json", "insert_after": 1},
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
            "/api/pipeline/insert-chapter",
            json={"checkpoint": "test.json", "insert_after": 1},
        )
        assert "text/event-stream" in resp.headers["content-type"]
        assert resp.headers.get("cache-control") == "no-cache"

    @pytest.mark.asyncio
    async def test_validates_insert_after_negative(self, client):
        """insert_after must be >= 0."""
        resp = await client.post(
            "/api/pipeline/insert-chapter",
            json={"checkpoint": "test.json", "insert_after": -1},
        )
        assert resp.status_code == 422  # Pydantic validation

    @pytest.mark.asyncio
    async def test_validates_word_count_range(self, client):
        """word_count must be between 100 and 20000."""
        resp = await client.post(
            "/api/pipeline/insert-chapter",
            json={"checkpoint": "test.json", "insert_after": 1, "word_count": 50},
        )
        assert resp.status_code == 422
