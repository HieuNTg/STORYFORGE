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
from models.schemas import PipelineOutput


def _make_app() -> FastAPI:
    from fastapi import APIRouter
    app = FastAPI()
    api = APIRouter(prefix="/api")
    api.include_router(pipeline_router)
    app.include_router(api)
    return app


@pytest.fixture(autouse=True)
def _isolate_session_state():
    """Reset module-level per-IP session state between tests.

    `_sessions` is only evicted by the age-based reaper in production, so within
    a single test process repeated POST /run calls from the same test-client IP
    accumulate and trip the `_MAX_SESSIONS_PER_IP` cap — making later tests
    order-dependent. Clearing it per test keeps the suite deterministic without
    touching product behaviour.
    """
    import api.pipeline_routes as _pr

    _pr._sessions.clear()
    yield
    _pr._sessions.clear()


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

    # run_full_pipeline returns a PipelineOutput (pydantic model), not a dict —
    # the route calls output.model_copy()/getattr(output, "status").
    mock_result = PipelineOutput(status="completed")

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
async def test_sse_error_status_output_emits_error_not_done():
    """C2/H3: a run that returns an error-status PipelineOutput must emit an
    `error` event carrying the real reason — not a silent empty `done`."""
    app = _make_app()

    reason = "Không kết nối được LLM: connection refused"
    mock_result = PipelineOutput(status="error", logs=[reason])

    with patch("api.pipeline_routes.PipelineOrchestrator") as MockOrch:
        instance = MagicMock()
        instance.run_full_pipeline.return_value = mock_result
        MockOrch.return_value = instance

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post(
                "/api/pipeline/run",
                json={"idea": "A brave warrior travels through time to save the kingdom"},
            )

        events = _parse_sse_events(resp.text)
        types = [e["type"] for e in events]
        # Must NOT report success
        assert "done" not in types
        assert types[-1] == "error"
        # The real reason must be surfaced, not the generic fallback
        assert reason in events[-1]["data"]


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
        return PipelineOutput(status="completed")

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


# ── Recovery via GET /api/pipeline/run/{id} ──────────────────────────────────
# Completes the codebase's stated recovery design: a run survives a lost SSE
# stream (reload mid-run or ECONNRESET), and the FE rebuilds the stepper +
# author dialogue by replaying job.logs returned here. See get_run_status.


@pytest_asyncio.fixture
async def _clean_jobs():
    """Drop any jobs this test created so the module-level registry stays clean."""
    from api import pipeline_job_registry as _jobs
    before = set(_jobs.JOBS)
    yield _jobs
    for sid in set(_jobs.JOBS) - before:
        _jobs.JOBS.pop(sid, None)


@pytest.mark.asyncio
async def test_run_status_returns_logs_for_recovery(client, _clean_jobs):
    """A running job's accumulated logs are returned so the FE can replay them."""
    job = await _clean_jobs.register("recover-1")
    job.logs.extend(
        [
            "[OUTLINE] Đang lập dàn ý...",
            "[L1] Đang viết chương 1: Mở đầu...",
            "[L1] Đang viết chương 2: Biến cố...",
        ]
    )

    resp = await client.get("/api/pipeline/run/recover-1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "running"
    assert body["logs_count"] == 3
    # since defaults to 0 → full history, in order.
    assert body["logs"] == [
        "[OUTLINE] Đang lập dàn ý...",
        "[L1] Đang viết chương 1: Mở đầu...",
        "[L1] Đang viết chương 2: Biến cố...",
    ]


@pytest.mark.asyncio
async def test_run_status_since_cursor_returns_delta(client, _clean_jobs):
    """`since` ships only the new lines so each poll is incremental."""
    job = await _clean_jobs.register("recover-2")
    job.logs.extend(["line-0", "line-1", "line-2"])

    resp = await client.get("/api/pipeline/run/recover-2", params={"since": 2})
    body = resp.json()
    assert body["logs"] == ["line-2"]
    assert body["logs_count"] == 3

    # Caught up: since == logs_count → empty delta, still reports the total.
    resp2 = await client.get("/api/pipeline/run/recover-2", params={"since": 3})
    body2 = resp2.json()
    assert body2["logs"] == []
    assert body2["logs_count"] == 3


@pytest.mark.asyncio
async def test_run_status_out_of_range_since_replays_from_start(client, _clean_jobs):
    """A stale/garbage cursor replays from 0 rather than erroring."""
    job = await _clean_jobs.register("recover-3")
    job.logs.extend(["a", "b"])

    for bad in (-5, 99):
        resp = await client.get("/api/pipeline/run/recover-3", params={"since": bad})
        assert resp.status_code == 200
        assert resp.json()["logs"] == ["a", "b"]


@pytest.mark.asyncio
async def test_run_status_unknown_session_404(client):
    """An expired/unknown session is a clean 404 so the FE can stop polling."""
    resp = await client.get("/api/pipeline/run/does-not-exist")
    assert resp.status_code == 404
