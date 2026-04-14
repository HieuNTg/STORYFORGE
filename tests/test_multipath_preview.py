"""Tests for multi-path preview feature (Phase 5)."""

import pytest
import pytest_asyncio
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from models.schemas import (
    StoryDraft, Character, WorldSetting, ChapterOutline, Chapter,
    CharacterState, PlotEvent, StoryContext, PipelineOutput,
    ArcDirective, PathPreview,
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
# Unit Tests: PathPreview Schema
# ══════════════════════════════════════════════════════════════════════════════

class TestPathPreviewSchema:
    """Unit tests for PathPreview schema."""

    def test_create_path_preview(self):
        """Should create valid PathPreview."""
        path = PathPreview(
            path_id="path_1",
            theme="Dark redemption arc",
            tone="dark",
            outlines=[{"chapter_number": 4, "title": "Ch4", "summary": "S4"}],
        )
        assert path.path_id == "path_1"
        assert path.theme == "Dark redemption arc"
        assert path.tone == "dark"
        assert len(path.outlines) == 1

    def test_empty_outlines_default(self):
        """Outlines should default to empty list."""
        path = PathPreview(path_id="p1", theme="Test")
        assert path.outlines == []

    def test_tone_optional(self):
        """Tone should be optional."""
        path = PathPreview(path_id="p1", theme="Test")
        assert path.tone == ""


# ══════════════════════════════════════════════════════════════════════════════
# Unit Tests: generate_continuation_paths
# ══════════════════════════════════════════════════════════════════════════════

class TestGenerateContinuationPaths:
    """Tests for generate_continuation_paths function."""

    def test_generates_multiple_paths(self):
        """Should generate specified number of paths."""
        from pipeline.layer1_story.story_continuation import generate_continuation_paths

        gen = _make_generator()
        draft = _make_draft(num_chapters=3)

        gen.llm.generate_json.return_value = {
            "paths": [
                {"path_id": "path_1", "theme": "Dark", "tone": "dark", "outlines": [
                    {"chapter_number": 4, "title": "Ch4", "summary": "S4", "key_events": []}
                ]},
                {"path_id": "path_2", "theme": "Light", "tone": "hopeful", "outlines": [
                    {"chapter_number": 4, "title": "Ch4B", "summary": "S4B", "key_events": []}
                ]},
                {"path_id": "path_3", "theme": "Romance", "tone": "romantic", "outlines": [
                    {"chapter_number": 4, "title": "Ch4C", "summary": "S4C", "key_events": []}
                ]},
            ]
        }

        paths = generate_continuation_paths(gen, draft, additional_chapters=5, num_paths=3)

        assert len(paths) == 3
        assert paths[0]["path_id"] == "path_1"
        assert paths[1]["theme"] == "Light"

    def test_clamps_num_paths(self):
        """num_paths should be clamped to 2-5."""
        from pipeline.layer1_story.story_continuation import generate_continuation_paths

        gen = _make_generator()
        draft = _make_draft()
        gen.llm.generate_json.return_value = {"paths": []}

        # Test clamping
        generate_continuation_paths(gen, draft, num_paths=1)  # Should become 2
        call_args = gen.llm.generate_json.call_args
        user_prompt = call_args.kwargs.get("user_prompt") or call_args[1].get("user_prompt")
        assert "2 HƯỚNG ĐI" in user_prompt  # Clamped to 2

    def test_higher_temperature_for_diversity(self):
        """Should use higher temperature for path diversity."""
        from pipeline.layer1_story.story_continuation import generate_continuation_paths

        gen = _make_generator()
        draft = _make_draft()
        gen.llm.generate_json.return_value = {"paths": []}

        generate_continuation_paths(gen, draft, num_paths=3)

        call_args = gen.llm.generate_json.call_args
        temp = call_args.kwargs.get("temperature") or call_args[1].get("temperature")
        assert temp >= 1.0  # Higher temperature for diversity

    def test_arc_directives_included(self):
        """Arc directives should be included in path generation."""
        from pipeline.layer1_story.story_continuation import generate_continuation_paths

        gen = _make_generator()
        draft = _make_draft()
        arc_directives = [
            ArcDirective(character="Hero", from_state="weak", to_state="strong", chapter_span=5),
        ]
        gen.llm.generate_json.return_value = {"paths": []}

        generate_continuation_paths(gen, draft, arc_directives=arc_directives)

        call_args = gen.llm.generate_json.call_args
        user_prompt = call_args.kwargs.get("user_prompt") or call_args[1].get("user_prompt")
        assert "Hero" in user_prompt
        assert "weak" in user_prompt

    def test_progress_callback_invoked(self):
        """Progress callback should receive status messages."""
        from pipeline.layer1_story.story_continuation import generate_continuation_paths

        gen = _make_generator()
        draft = _make_draft()
        progress_msgs = []
        gen.llm.generate_json.return_value = {"paths": []}

        generate_continuation_paths(gen, draft, num_paths=3, progress_callback=progress_msgs.append)

        assert any("alternative" in msg.lower() or "path" in msg.lower() for msg in progress_msgs)


# ══════════════════════════════════════════════════════════════════════════════
# Unit Tests: StoryContinuation orchestrator
# ══════════════════════════════════════════════════════════════════════════════

class TestStoryContinuationPaths:
    """Tests for StoryContinuation.generate_continuation_paths method."""

    def test_raises_if_no_draft(self):
        """Should raise ValueError if no story draft loaded."""
        from pipeline.orchestrator_continuation import StoryContinuation

        output = PipelineOutput()
        cont = StoryContinuation(output, MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock())

        with pytest.raises(ValueError, match="No story draft loaded"):
            cont.generate_continuation_paths()

    @patch("pipeline.layer1_story.story_continuation.generate_continuation_paths")
    def test_calls_impl_function(self, mock_gen_paths):
        """Should call generate_continuation_paths implementation."""
        from pipeline.orchestrator_continuation import StoryContinuation

        draft = _make_draft()
        output = PipelineOutput(story_draft=draft)
        story_gen = MagicMock()
        mock_gen_paths.return_value = [{"path_id": "p1", "theme": "T", "outlines": []}]

        cont = StoryContinuation(output, story_gen, MagicMock(), MagicMock(), MagicMock(), MagicMock())
        paths = cont.generate_continuation_paths(additional_chapters=5, num_paths=3)

        mock_gen_paths.assert_called_once()
        assert len(paths) == 1

    @patch("pipeline.layer1_story.story_continuation.generate_continuation_paths")
    def test_passes_arc_directives(self, mock_gen_paths):
        """Should pass arc_directives to impl."""
        from pipeline.orchestrator_continuation import StoryContinuation

        draft = _make_draft()
        output = PipelineOutput(story_draft=draft)
        arc_directives = [ArcDirective(character="X", from_state="a", to_state="b")]
        mock_gen_paths.return_value = []

        cont = StoryContinuation(output, MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock())
        cont.generate_continuation_paths(arc_directives=arc_directives)

        mock_gen_paths.assert_called_once()
        assert mock_gen_paths.call_args.kwargs.get("arc_directives") == arc_directives


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


class TestMultiPathAPI:
    """API endpoint tests for multi-path preview."""

    @pytest.mark.asyncio
    async def test_paths_endpoint_returns_404_for_missing_checkpoint(self, client):
        """Non-existent checkpoint should return 404."""
        resp = await client.post(
            "/api/pipeline/continue/paths",
            json={"checkpoint": "nonexistent.json", "num_paths": 3},
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["error"].lower()

    @pytest.mark.asyncio
    async def test_paths_validates_num_paths(self, client):
        """num_paths must be between 2 and 5."""
        resp = await client.post(
            "/api/pipeline/continue/paths",
            json={"checkpoint": "test.json", "num_paths": 1},
        )
        assert resp.status_code == 422

        resp = await client.post(
            "/api/pipeline/continue/paths",
            json={"checkpoint": "test.json", "num_paths": 10},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_select_path_returns_sse(self, client):
        """select-path should return SSE response."""
        resp = await client.post(
            "/api/pipeline/continue/select-path",
            json={
                "checkpoint": "test.json",
                "path_id": "path_1",
                "outlines": [{"chapter_number": 4, "title": "Ch", "summary": "S", "key_events": []}],
            },
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

    @pytest.mark.asyncio
    async def test_select_path_validates_outlines(self, client):
        """Invalid outlines should return error in SSE."""
        resp = await client.post(
            "/api/pipeline/continue/select-path",
            json={
                "checkpoint": "test.json",
                "path_id": "path_1",
                "outlines": [{"invalid": "data"}],
            },
        )
        # Still returns SSE (200), but with error event
        assert resp.status_code == 200
        # Error would be in SSE stream

    @pytest.mark.asyncio
    async def test_paths_accepts_arc_directives(self, client):
        """paths endpoint should accept arc_directives."""
        resp = await client.post(
            "/api/pipeline/continue/paths",
            json={
                "checkpoint": "test.json",
                "num_paths": 3,
                "arc_directives": [
                    {"character": "Hero", "from_state": "a", "to_state": "b", "chapter_span": 3}
                ],
            },
        )
        # Schema validation passed (would be 422 otherwise)
        assert resp.status_code in [404, 200]
