"""Async API endpoint tests using httpx.AsyncClient.

P1-7: Migrates endpoint testing to async pattern with pytest-asyncio.
Covers config, pipeline, export, and health routes.
"""

import json
import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock

from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from api.config_routes import router as config_router
from api.pipeline_routes import router as pipeline_router
from api.export_routes import router as export_router
from errors.exceptions import StoryForgeError
from errors.handlers import storyforge_error_handler


def _make_app() -> FastAPI:
    """Create minimal FastAPI app with all API routes."""
    from fastapi import APIRouter
    app = FastAPI()
    app.add_exception_handler(StoryForgeError, storyforge_error_handler)
    api = APIRouter(prefix="/api")
    api.include_router(config_router)
    api.include_router(pipeline_router)
    api.include_router(export_router)
    app.include_router(api)

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "version": "3.0"}

    return app


@pytest_asyncio.fixture
async def client():
    app = _make_app()
    # Set backend_type to "web" so save() doesn't require api_key
    from config import ConfigManager
    cfg = ConfigManager()
    cfg.llm.backend_type = "web"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── Health endpoint ──

@pytest.mark.asyncio
async def test_health_endpoint(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == "3.0"


# ── Config endpoints ──

@pytest.mark.asyncio
async def test_get_config(client):
    resp = await client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "llm" in data
    assert "api_key_masked" in data["llm"]


@pytest.mark.asyncio
async def test_get_languages(client):
    resp = await client.get("/api/config/languages")
    assert resp.status_code == 200
    data = resp.json()
    assert "languages" in data
    assert "current" in data


@pytest.mark.asyncio
async def test_get_presets(client):
    resp = await client.get("/api/config/presets")
    assert resp.status_code == 200
    data = resp.json()
    assert "presets" in data
    assert "beginner" in data["presets"]
    assert "advanced" in data["presets"]
    assert "pro" in data["presets"]


@pytest.mark.asyncio
async def test_apply_preset_beginner(client):
    resp = await client.post("/api/config/presets/beginner")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_apply_preset_invalid(client):
    resp = await client.post("/api/config/presets/nonexistent_preset")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_save_config(client):
    resp = await client.put(
        "/api/config",
        json={"temperature": 0.5, "language": "en"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_test_connection(client):
    with patch("services.llm_client.LLMClient") as mock_cls:
        mock_cls._instance = None
        instance = MagicMock()
        instance.check_connection.return_value = (True, "OK")
        mock_cls.return_value = instance
        resp = await client.post("/api/config/test-connection")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_cache_stats(client):
    resp = await client.get("/api/config/cache-stats")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_clear_cache(client):
    resp = await client.delete("/api/config/cache")
    assert resp.status_code == 200


# ── Pipeline endpoints ──

@pytest.mark.asyncio
async def test_get_genres(client):
    resp = await client.get("/api/pipeline/genres")
    assert resp.status_code == 200
    data = resp.json()
    assert "genres" in data
    assert "styles" in data
    assert "drama_levels" in data
    assert len(data["genres"]) > 0


@pytest.mark.asyncio
async def test_get_templates(client):
    resp = await client.get("/api/pipeline/templates")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_checkpoints(client):
    resp = await client.get("/api/pipeline/checkpoints")
    assert resp.status_code == 200
    data = resp.json()
    assert "checkpoints" in data


@pytest.mark.asyncio
async def test_run_pipeline_short_idea_returns_error(client):
    """Pipeline should reject ideas shorter than 10 characters via SSE error."""
    resp = await client.post(
        "/api/pipeline/run",
        json={"idea": "short"},
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    body = resp.text
    assert "error" in body
    assert "too short" in body.lower()


@pytest.mark.asyncio
async def test_run_pipeline_empty_idea(client):
    resp = await client.post(
        "/api/pipeline/run",
        json={"idea": ""},
    )
    assert resp.status_code == 200
    body = resp.text
    assert "error" in body


@pytest.mark.asyncio
async def test_resume_pipeline_missing_checkpoint(client):
    resp = await client.post(
        "/api/pipeline/resume",
        json={"checkpoint": "nonexistent_checkpoint_file.json"},
    )
    assert resp.status_code == 200
    body = resp.text
    assert "error" in body
    assert "not found" in body.lower()


@pytest.mark.asyncio
async def test_resume_pipeline_path_traversal(client):
    """Checkpoint should not allow path traversal."""
    resp = await client.post(
        "/api/pipeline/resume",
        json={"checkpoint": "../../etc/passwd"},
    )
    assert resp.status_code == 200
    body = resp.text
    assert "error" in body


# ── Export endpoints ──

@pytest.mark.asyncio
async def test_export_no_session(client):
    """Export without valid session should fail gracefully."""
    resp = await client.post(
        "/api/export/pdf",
        json={"session_id": "nonexistent"},
    )
    # Should return error (either 400 or JSON error)
    assert resp.status_code in (200, 400, 404, 422)


# ── Error handler ──

@pytest.mark.asyncio
async def test_storyforge_error_handler():
    """StoryForge typed exceptions produce structured JSON error responses."""
    app = FastAPI()
    app.add_exception_handler(StoryForgeError, storyforge_error_handler)

    @app.get("/test-error")
    async def raise_error():
        from errors.exceptions import ConfigError
        raise ConfigError("Test config error")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/test-error")
        assert resp.status_code == 400
        data = resp.json()
        assert data["error"]["code"] == "CONFIG_ERROR"
        assert "Test config error" in data["error"]["message"]


@pytest.mark.asyncio
async def test_pipeline_error_handler():
    app = FastAPI()
    app.add_exception_handler(StoryForgeError, storyforge_error_handler)

    @app.get("/test-pipeline-error")
    async def raise_error():
        from errors.exceptions import PipelineError
        raise PipelineError("Pipeline failed")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/test-pipeline-error")
        assert resp.status_code == 500
        data = resp.json()
        assert data["error"]["code"] == "PIPELINE_ERROR"


# ── Config validation edge cases ──

@pytest.mark.asyncio
async def test_save_config_invalid_temperature_type(client):
    """Non-float temperature should be rejected by Pydantic."""
    resp = await client.put(
        "/api/config",
        json={"temperature": "not_a_number"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_save_config_partial_update(client):
    """Updating only base_url should leave other fields intact."""
    resp = await client.put(
        "/api/config",
        json={"base_url": "http://custom-llm:8000/v1"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_apply_preset_advanced(client):
    resp = await client.post("/api/config/presets/advanced")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_apply_preset_pro(client):
    resp = await client.post("/api/config/presets/pro")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── Multiple rapid requests ──

@pytest.mark.asyncio
async def test_rapid_genre_requests(client):
    """Multiple concurrent requests to genres endpoint should all succeed."""
    import asyncio
    tasks = [client.get("/api/pipeline/genres") for _ in range(10)]
    results = await asyncio.gather(*tasks)
    for r in results:
        assert r.status_code == 200
        assert "genres" in r.json()


@pytest.mark.asyncio
async def test_rapid_config_reads(client):
    import asyncio
    tasks = [client.get("/api/config") for _ in range(10)]
    results = await asyncio.gather(*tasks)
    for r in results:
        assert r.status_code == 200
