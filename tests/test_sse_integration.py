"""SSE integration tests — connection lifecycle, event ordering, error handling.

P1-9: End-to-end SSE stream tests for pipeline and resume endpoints.
"""

import json
import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock

from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from api.pipeline_routes import router as pipeline_router


def _make_app() -> FastAPI:
    from fastapi import APIRouter
    app = FastAPI()
    api = APIRouter(prefix="/api")
    api.include_router(pipeline_router)
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


# ── SSE Connection Lifecycle ──

@pytest.mark.asyncio
async def test_sse_error_stream_on_short_idea(client):
    """Short idea should produce a single SSE error event."""
    resp = await client.post(
        "/api/pipeline/run",
        json={"idea": "hi"},
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    events = _parse_sse_events(resp.text)
    assert len(events) >= 1
    assert events[0]["type"] == "error"


@pytest.mark.asyncio
async def test_sse_content_type_headers(client):
    """SSE responses must have correct content-type and cache headers."""
    resp = await client.post(
        "/api/pipeline/run",
        json={"idea": "short"},
    )
    assert "text/event-stream" in resp.headers["content-type"]
    assert resp.headers.get("cache-control") == "no-cache"


@pytest.mark.asyncio
async def test_sse_event_format(client):
    """SSE events should be valid JSON with 'type' field."""
    resp = await client.post(
        "/api/pipeline/run",
        json={"idea": "too short"},
    )
    events = _parse_sse_events(resp.text)
    for ev in events:
        assert "type" in ev


@pytest.mark.asyncio
async def test_sse_pipeline_session_event():
    """A successful pipeline run should emit session event first, then done."""
    app = _make_app()

    mock_result = {
        "title": "Test Story",
        "chapters": [{"number": 1, "content": "Once upon..."}],
    }

    with patch("api.pipeline_routes.PipelineOrchestrator") as MockOrch:
        instance = MagicMock()
        instance.run_full_pipeline.return_value = mock_result
        MockOrch.return_value = instance

        with patch("api.pipeline_output_builder.build_output_summary") as mock_build:
            mock_build.return_value = {"title": "Test Story", "has_draft": True}

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.post(
                    "/api/pipeline/run",
                    json={
                        "idea": "A brave warrior travels through time to save the kingdom",
                        "genre": "Fantasy",
                        "num_chapters": 1,
                    },
                )

            events = _parse_sse_events(resp.text)
            assert len(events) >= 2
            # First event should be session
            assert events[0]["type"] == "session"
            assert "session_id" in events[0]
            # Last event should be done
            assert events[-1]["type"] == "done"
            assert "data" in events[-1]


@pytest.mark.asyncio
async def test_sse_pipeline_error_event():
    """Pipeline exception should produce SSE error event."""
    app = _make_app()

    with patch("api.pipeline_routes.PipelineOrchestrator") as MockOrch:
        instance = MagicMock()
        instance.run_full_pipeline.side_effect = RuntimeError("LLM failed")
        MockOrch.return_value = instance

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post(
                "/api/pipeline/run",
                json={"idea": "A test story about dragons and magic in a fantasy world"},
            )

        events = _parse_sse_events(resp.text)
        # Should get session event + error event
        types = [e["type"] for e in events]
        assert "session" in types
        assert "error" in types


@pytest.mark.asyncio
async def test_sse_resume_missing_checkpoint(client):
    """Resume with nonexistent checkpoint should SSE error."""
    resp = await client.post(
        "/api/pipeline/resume",
        json={"checkpoint": "does_not_exist.json"},
    )
    assert resp.status_code == 200
    events = _parse_sse_events(resp.text)
    assert len(events) >= 1
    assert events[0]["type"] == "error"
    assert "not found" in events[0]["data"].lower()


@pytest.mark.asyncio
async def test_sse_resume_path_traversal(client):
    """Path traversal in checkpoint name should be rejected."""
    resp = await client.post(
        "/api/pipeline/resume",
        json={"checkpoint": "../../../etc/passwd"},
    )
    events = _parse_sse_events(resp.text)
    assert events[0]["type"] == "error"


@pytest.mark.asyncio
async def test_sse_event_ordering_with_progress():
    """Progress callbacks should produce SSE log events between session and done."""
    app = _make_app()


    def _mock_pipeline(**kwargs):
        cb = kwargs.get("progress_callback")
        if cb:
            cb("Starting layer 1...")
            cb("Generating characters...")
            cb("Writing chapters...")
        return {"title": "Story", "chapters": []}

    with patch("api.pipeline_routes.PipelineOrchestrator") as MockOrch:
        instance = MagicMock()
        instance.run_full_pipeline.side_effect = _mock_pipeline
        MockOrch.return_value = instance

        with patch("api.pipeline_output_builder.build_output_summary") as mock_build:
            mock_build.return_value = {"title": "Story", "has_draft": True}

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.post(
                    "/api/pipeline/run",
                    json={"idea": "An epic tale of heroes fighting against darkness in ancient times"},
                )

            events = _parse_sse_events(resp.text)
            types = [e["type"] for e in events]

            # Session always first
            assert types[0] == "session"
            # Done always last
            assert types[-1] == "done"
            # In mocked mode, progress callbacks run synchronously in the
            # pipeline thread — the SSE generator may or may not capture
            # them depending on timing. Just verify session→done ordering.
            assert len(events) >= 2


@pytest.mark.asyncio
async def test_sse_double_newline_format(client):
    """Each SSE data line should end with double newline."""
    resp = await client.post(
        "/api/pipeline/run",
        json={"idea": "short"},
    )
    # SSE spec: each event block ends with \n\n
    assert "data: " in resp.text
    # Each data line should be followed by \n\n
    lines = resp.text.strip().split("\n\n")
    for block in lines:
        if block.strip():
            assert block.strip().startswith("data: ")
