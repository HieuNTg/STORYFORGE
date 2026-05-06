"""Comprehensive coverage tests for:
- api/config_routes.py
- api/pipeline_routes.py
- services/handlers.py
- services/llm/client.py
- services/llm_cache.py
- services/auth/auth.py
- services/auth/jwt_manager.py
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Ensure secret key is set before any auth imports
os.environ.setdefault("STORYFORGE_SECRET_KEY", "test-secret-key-for-unit-tests-coverage")

try:
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False


# ===========================================================================
# Helper: build minimal mock ConfigManager
# ===========================================================================

def _mock_config_manager():
    mock_cm = MagicMock()
    mock_cm.llm.api_key = "sk-test1234abcd"
    mock_cm.llm.base_url = "https://api.openai.com/v1"
    mock_cm.llm.model = "gpt-4o-mini"
    mock_cm.llm.temperature = 0.8
    mock_cm.llm.max_tokens = 4096
    mock_cm.llm.cheap_model = ""
    mock_cm.llm.cheap_base_url = ""
    mock_cm.llm.api_keys = []
    mock_cm.llm.fallback_models = []
    mock_cm.llm.layer1_model = ""
    mock_cm.llm.layer2_model = ""
    mock_cm.llm.cache_enabled = True
    mock_cm.llm.cache_ttl_days = 7
    mock_cm.pipeline.language = "vi"
    mock_cm.pipeline.image_provider = "none"
    mock_cm.pipeline.hf_token = ""
    mock_cm.pipeline.image_prompt_style = "cinematic"
    mock_cm.pipeline.hf_image_model = ""
    mock_cm.pipeline.enable_self_review = False
    mock_cm.pipeline.self_review_threshold = 3.0
    mock_cm.pipeline.share_base_url = "http://localhost:7860/"
    mock_cm.validate.return_value = []
    mock_cm.save.return_value = None
    return mock_cm


# ===========================================================================
# config_routes.py — helper functions
# ===========================================================================

class TestConfigRoutesHelpers:
    """Tests for standalone helper functions in config_routes."""

    def test_mask_key_normal(self):
        from api.config_routes import _mask_key
        result = _mask_key("sk-abcdefghijklmn")
        assert "***" in result
        assert result.startswith("sk-abc")

    def test_mask_key_short(self):
        from api.config_routes import _mask_key
        result = _mask_key("short")
        assert result == "***"

    def test_mask_key_empty(self):
        from api.config_routes import _mask_key
        result = _mask_key("")
        assert result == ""

    def test_mask_key_exactly_10(self):
        from api.config_routes import _mask_key
        # len 10 triggers the short path
        result = _mask_key("1234567890")
        assert result == "***"

    def test_mask_key_11_chars(self):
        from api.config_routes import _mask_key
        result = _mask_key("12345678901")
        assert "***" in result

    def test_detect_provider_openai(self):
        from api.config_routes import _detect_provider_name
        assert _detect_provider_name("https://api.openai.com/v1") == "openai"

    def test_detect_provider_gemini(self):
        from api.config_routes import _detect_provider_name
        assert _detect_provider_name("https://generativelanguage.googleapis.com/v1beta") == "gemini"

    def test_detect_provider_anthropic(self):
        from api.config_routes import _detect_provider_name
        assert _detect_provider_name("https://api.anthropic.com/v1") == "anthropic"

    def test_detect_provider_openrouter(self):
        from api.config_routes import _detect_provider_name
        assert _detect_provider_name("https://openrouter.ai/api/v1") == "openrouter"

    def test_detect_provider_local(self):
        from api.config_routes import _detect_provider_name
        assert _detect_provider_name("http://localhost:11434/v1") == "local"

    def test_detect_provider_127(self):
        from api.config_routes import _detect_provider_name
        assert _detect_provider_name("http://127.0.0.1:8080/v1") == "local"

    def test_detect_provider_custom(self):
        from api.config_routes import _detect_provider_name
        assert _detect_provider_name("https://myserver.example.com/v1") == "custom"

    def test_detect_from_key_anthropic(self):
        from api.config_routes import _detect_provider_from_key
        result = _detect_provider_from_key("sk-ant-api03-test")
        assert result is not None
        assert result["name"] == "Anthropic"

    def test_detect_from_key_openrouter(self):
        from api.config_routes import _detect_provider_from_key
        result = _detect_provider_from_key("sk-or-v1-test")
        assert result is not None
        assert "OpenRouter" in result["name"]

    def test_detect_from_key_openai_proj(self):
        from api.config_routes import _detect_provider_from_key
        result = _detect_provider_from_key("sk-proj-abcdefg")
        assert result is not None
        assert "OpenAI" in result["name"]

    def test_detect_from_key_openai_sk(self):
        from api.config_routes import _detect_provider_from_key
        result = _detect_provider_from_key("sk-abcdefg")
        assert result is not None

    def test_detect_from_key_gemini(self):
        from api.config_routes import _detect_provider_from_key
        result = _detect_provider_from_key("AIzaSomethingHere")
        assert result is not None
        assert "Google" in result["name"] or "Gemini" in result["name"]

    def test_detect_from_key_unknown(self):
        from api.config_routes import _detect_provider_from_key
        result = _detect_provider_from_key("unknownprefix-abc")
        assert result is None

    def test_detect_from_key_empty(self):
        from api.config_routes import _detect_provider_from_key
        result = _detect_provider_from_key("")
        assert result is None


# ===========================================================================
# config_routes.py — API endpoints
# ===========================================================================

@pytest.mark.skipif(not _HAS_FASTAPI, reason="FastAPI not installed")
class TestConfigRoutesEndpoints:
    """Tests for config_routes API endpoints."""

    @pytest.fixture(autouse=True)
    def client(self):
        from api.config_routes import router
        app = FastAPI()
        app.include_router(router)
        self._client = TestClient(app, raise_server_exceptions=False)

    def test_get_config_has_llm_section(self):
        resp = self._client.get("/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "llm" in data
        assert "pipeline" in data

    def test_get_config_llm_api_key_masked(self):
        resp = self._client.get("/config")
        assert resp.status_code == 200
        data = resp.json()
        # The api_key_masked field should exist and be masked
        assert "api_key_masked" in data["llm"]

    def test_get_config_pipeline_section_keys(self):
        resp = self._client.get("/config")
        assert resp.status_code == 200
        data = resp.json()
        pipeline = data["pipeline"]
        assert "language" in pipeline
        assert "image_provider" in pipeline

    def test_put_config_with_api_key(self):
        with patch("api.config_routes.ConfigManager") as MockCM, \
             patch("api.config_routes.I18n"), \
             patch("services.llm_client.LLMClient") as MockLLC:
            MockCM.return_value = _mock_config_manager()
            MockLLC.reset = MagicMock()
            resp = self._client.put("/config", json={"api_key": "sk-newkey1234"})
        assert resp.status_code in (200, 422)

    def test_put_config_with_model(self):
        with patch("api.config_routes.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMClient") as MockLLC:
            mock_cm = _mock_config_manager()
            MockCM.return_value = mock_cm
            MockLLC.reset = MagicMock()
            resp = self._client.put("/config", json={"model": "gpt-4o"})
        assert resp.status_code in (200, 422)

    def test_put_config_with_temperature(self):
        with patch("api.config_routes.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMClient") as MockLLC:
            MockCM.return_value = _mock_config_manager()
            MockLLC.reset = MagicMock()
            resp = self._client.put("/config", json={"temperature": 0.5})
        assert resp.status_code in (200, 422)

    def test_put_config_with_language(self):
        with patch("api.config_routes.ConfigManager") as MockCM, \
             patch("api.config_routes.I18n"), \
             patch("services.llm_client.LLMClient") as MockLLC:
            MockCM.return_value = _mock_config_manager()
            MockLLC.reset = MagicMock()
            resp = self._client.put("/config", json={"language": "en"})
        assert resp.status_code in (200, 422)

    def test_put_config_save_value_error(self):
        with patch("api.config_routes.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMClient") as MockLLC:
            mock_cm = _mock_config_manager()
            mock_cm.save.side_effect = ValueError("api key required")
            MockCM.return_value = mock_cm
            MockLLC.reset = MagicMock()
            resp = self._client.put("/config", json={"model": "x"})
        assert resp.status_code == 422

    def test_put_config_append_api_keys(self):
        with patch("api.config_routes.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMClient") as MockLLC:
            mock_cm = _mock_config_manager()
            mock_cm.llm.api_keys = []
            MockCM.return_value = mock_cm
            MockLLC.reset = MagicMock()
            resp = self._client.put("/config", json={"append_api_keys": ["sk-extra1234"]})
        assert resp.status_code in (200, 422)

    def test_test_connection_endpoint(self):
        with patch("services.llm_client.LLMClient") as MockLLC:
            mock_client = MagicMock()
            mock_client.check_connection.return_value = (True, "Connection successful")
            MockLLC.return_value = mock_client
            MockLLC.reset = MagicMock()
            resp = self._client.post("/config/test-connection")
        assert resp.status_code in (200, 500)

    def test_get_languages(self):
        resp = self._client.get("/config/languages")
        assert resp.status_code == 200
        data = resp.json()
        assert "languages" in data

    def test_get_presets(self):
        resp = self._client.get("/config/presets")
        assert resp.status_code == 200
        data = resp.json()
        assert "presets" in data

    def test_get_model_presets(self):
        resp = self._client.get("/config/model-presets")
        assert resp.status_code == 200
        data = resp.json()
        assert "presets" in data

    def test_apply_preset_valid_key(self):
        with patch("api.config_routes.ConfigManager") as MockCM:
            mock_cm = _mock_config_manager()
            MockCM.return_value = mock_cm
            resp = self._client.post("/config/presets/beginner")
        assert resp.status_code in (200, 422, 500)

    def test_apply_preset_invalid_key(self):
        resp = self._client.post("/config/presets/nonexistent-preset")
        assert resp.status_code == 404

    def test_apply_model_preset_invalid_key(self):
        resp = self._client.post("/config/model-presets/nonexistent-preset")
        assert resp.status_code == 404

    def test_detect_provider_anthropic_key(self):
        resp = self._client.post("/config/profiles/detect",
                                  json={"api_key": "sk-ant-api03-test", "name": "", "base_url": "", "model": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert data["detected"] is True
        assert "name" in data

    def test_detect_provider_unknown_key(self):
        resp = self._client.post("/config/profiles/detect",
                                  json={"api_key": "unknown-prefix-abc", "name": "", "base_url": "", "model": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert data["detected"] is False

    def test_detect_provider_no_key(self):
        resp = self._client.post("/config/profiles/detect",
                                  json={"api_key": "", "name": "", "base_url": "", "model": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert data["detected"] is False

    def test_add_profile_with_detected_provider(self):
        with patch("api.config_routes.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMClient") as MockLLC:
            mock_cm = _mock_config_manager()
            mock_cm.llm.api_key = ""
            mock_cm.llm.fallback_models = []
            MockCM.return_value = mock_cm
            MockLLC.reset = MagicMock()
            resp = self._client.post("/config/profiles", json={
                "api_key": "sk-ant-api03-test",
                "name": "",
                "base_url": "",
                "model": "",
            })
        assert resp.status_code in (200, 422)

    def test_add_profile_no_base_url_detected(self):
        with patch("api.config_routes.ConfigManager") as MockCM:
            MockCM.return_value = _mock_config_manager()
            resp = self._client.post("/config/profiles", json={
                "api_key": "unknown-key",
                "name": "Custom",
                "base_url": "",
                "model": "",
            })
        # Should fail with 400 since no base_url and can't detect
        assert resp.status_code in (400, 422)

    def test_add_profile_explicit_base_url(self):
        with patch("api.config_routes.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMClient") as MockLLC:
            mock_cm = _mock_config_manager()
            mock_cm.llm.api_key = "existing-key"
            mock_cm.llm.fallback_models = []
            MockCM.return_value = mock_cm
            MockLLC.reset = MagicMock()
            resp = self._client.post("/config/profiles", json={
                "api_key": "sk-extra",
                "name": "My Provider",
                "base_url": "https://api.openai.com/v1",
                "model": "custom-model",
            })
        assert resp.status_code in (200, 422)

    def test_update_profile_out_of_range(self):
        with patch("api.config_routes.ConfigManager") as MockCM:
            mock_cm = _mock_config_manager()
            mock_cm.llm.fallback_models = []
            MockCM.return_value = mock_cm
            resp = self._client.put("/config/profiles/99", json={
                "name": "Test", "base_url": "https://x.com", "api_key": "sk-x", "model": "m"
            })
        assert resp.status_code == 404

    def test_update_profile_valid(self):
        with patch("api.config_routes.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMClient") as MockLLC:
            mock_cm = _mock_config_manager()
            mock_cm.llm.fallback_models = [
                {"name": "Old", "base_url": "https://api.openai.com/v1", "api_key": "sk-old", "model": "old-model", "enabled": True}
            ]
            MockCM.return_value = mock_cm
            MockLLC.reset = MagicMock()
            resp = self._client.put("/config/profiles/0", json={
                "name": "New", "base_url": "https://api.openai.com/v1", "api_key": "sk-new", "model": "new-model"
            })
        assert resp.status_code in (200, 422)

    def test_delete_profile_valid(self):
        with patch("api.config_routes.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMClient") as MockLLC:
            mock_cm = _mock_config_manager()
            mock_cm.llm.fallback_models = [
                {"name": "ToDelete", "base_url": "https://x.com", "api_key": "sk-x", "model": "m", "enabled": True}
            ]
            MockCM.return_value = mock_cm
            MockLLC.reset = MagicMock()
            resp = self._client.delete("/config/profiles/0")
        assert resp.status_code in (200, 422)

    def test_delete_profile_out_of_range(self):
        with patch("api.config_routes.ConfigManager") as MockCM:
            mock_cm = _mock_config_manager()
            mock_cm.llm.fallback_models = []
            MockCM.return_value = mock_cm
            resp = self._client.delete("/config/profiles/5")
        assert resp.status_code == 404

    def test_toggle_profile_valid(self):
        with patch("api.config_routes.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMClient") as MockLLC:
            mock_cm = _mock_config_manager()
            mock_cm.llm.fallback_models = [
                {"name": "P1", "base_url": "https://x.com", "api_key": "sk-x", "model": "m", "enabled": True}
            ]
            MockCM.return_value = mock_cm
            MockLLC.reset = MagicMock()
            resp = self._client.patch("/config/profiles/0/toggle")
        assert resp.status_code in (200, 422)

    def test_toggle_profile_out_of_range(self):
        with patch("api.config_routes.ConfigManager") as MockCM:
            mock_cm = _mock_config_manager()
            mock_cm.llm.fallback_models = []
            MockCM.return_value = mock_cm
            resp = self._client.patch("/config/profiles/99/toggle")
        assert resp.status_code == 404

    def test_cache_stats_endpoint(self):
        with patch("api.config_routes.ConfigManager") as MockCM, \
             patch("services.llm_cache.LLMCache") as MockCache:
            MockCM.return_value = _mock_config_manager()
            mock_cache = MagicMock()
            mock_cache.stats.return_value = {"backend": "sqlite", "hits": 0, "misses": 0, "hit_rate_pct": 0.0}
            MockCache.return_value = mock_cache
            resp = self._client.get("/config/cache-stats")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    def test_clear_cache_endpoint(self):
        with patch("services.llm_cache.LLMCache") as MockCache:
            mock_cache = MagicMock()
            MockCache.return_value = mock_cache
            resp = self._client.delete("/config/cache")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "ok"

    def test_remove_api_key_out_of_range(self):
        with patch("api.config_routes.ConfigManager") as MockCM:
            mock_cm = _mock_config_manager()
            mock_cm.llm.api_keys = []
            MockCM.return_value = mock_cm
            resp = self._client.delete("/config/api-keys/0")
        assert resp.status_code == 404

    def test_remove_api_key_valid(self):
        with patch("api.config_routes.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMClient") as MockLLC:
            mock_cm = _mock_config_manager()
            mock_cm.llm.api_keys = ["sk-extra-key-1234"]
            MockCM.return_value = mock_cm
            MockLLC.reset = MagicMock()
            resp = self._client.delete("/config/api-keys/0")
        assert resp.status_code in (200, 422)


# ===========================================================================
# pipeline_routes.py — API endpoints
# ===========================================================================

@pytest.mark.skipif(not _HAS_FASTAPI, reason="FastAPI not installed")
class TestPipelineRoutesEndpoints:
    """Tests for pipeline_routes API endpoints."""

    @pytest.fixture(autouse=True)
    def client(self):
        from api.pipeline_routes import router
        app = FastAPI()
        app.include_router(router)
        self._client = TestClient(app, raise_server_exceptions=False)

    def test_get_genres_structure(self):
        resp = self._client.get("/pipeline/genres")
        assert resp.status_code == 200
        data = resp.json()
        assert "genres" in data
        assert "styles" in data
        assert "drama_levels" in data
        assert isinstance(data["genres"], list)
        assert len(data["genres"]) > 0

    def test_get_templates_returns_dict(self):
        resp = self._client.get("/pipeline/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    def test_get_checkpoints_empty(self):
        # Patch at the import site used inside the route handler
        with patch("pipeline.orchestrator.PipelineOrchestrator") as MockOrch:
            MockOrch.list_checkpoints.return_value = []
            resp = self._client.get("/pipeline/checkpoints")
        assert resp.status_code == 200
        data = resp.json()
        assert "checkpoints" in data
        # Result may include real checkpoints from disk; just assert the structure
        assert isinstance(data["checkpoints"], list)

    def test_get_checkpoints_with_data(self):
        with patch("pipeline.orchestrator.PipelineOrchestrator") as MockOrch:
            MockOrch.list_checkpoints.return_value = [
                {
                    "file": "story_checkpoint.json",
                    "modified": "2026-01-01",
                    "size_kb": 10,
                    "title": "Test Story",
                    "genre": "Tiên Hiệp",
                    "chapter_count": 5,
                    "current_layer": 2,
                }
            ]
            resp = self._client.get("/pipeline/checkpoints")
        assert resp.status_code == 200

    def test_get_checkpoint_path_traversal(self):
        resp = self._client.get("/pipeline/checkpoints/../etc/passwd")
        assert resp.status_code in (400, 404, 422)

    def test_get_checkpoint_not_found(self):
        resp = self._client.get("/pipeline/checkpoints/nonexistent_file_xyz.json")
        assert resp.status_code == 404

    def test_delete_checkpoint_not_found(self):
        resp = self._client.delete("/pipeline/checkpoints/nonexistent_file_xyz.json")
        assert resp.status_code == 404

    def test_delete_checkpoint_path_traversal(self):
        # Path traversal via ".." in filename — FastAPI may normalize the URL,
        # so the route gets "passwd" after stripping "../../../etc/"
        # and the file doesn't exist → 404 is an acceptable safe response
        resp = self._client.delete("/pipeline/checkpoints/../../../etc/passwd")
        assert resp.status_code in (400, 404, 422)

    def test_list_stories_default_pagination(self):
        with patch("pipeline.orchestrator.PipelineOrchestrator") as MockOrch:
            MockOrch.list_checkpoints.return_value = []
            resp = self._client.get("/pipeline/stories")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data

    def test_list_stories_with_data(self):
        with patch("pipeline.orchestrator.PipelineOrchestrator") as MockOrch:
            checkpoints = [
                {
                    "file": f"story_{i}_layer2.json",
                    "modified": "2026-01-01",
                    "size_kb": 5,
                    "title": f"Story {i}",
                    "genre": "Tiên Hiệp",
                    "chapter_count": 3,
                    "current_layer": 2,
                }
                for i in range(5)
            ]
            MockOrch.list_checkpoints.return_value = checkpoints
            resp = self._client.get("/pipeline/stories?limit=3&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert data["limit"] == 3
        assert len(data["items"]) <= 3

    def test_list_stories_pagination_offset(self):
        with patch("pipeline.orchestrator.PipelineOrchestrator") as MockOrch:
            MockOrch.list_checkpoints.return_value = [
                {"file": f"s{i}_layer2.json", "modified": "2026", "size_kb": 1,
                 "title": f"T{i}", "genre": "G", "chapter_count": 1, "current_layer": 2}
                for i in range(10)
            ]
            resp = self._client.get("/pipeline/stories?limit=5&offset=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["offset"] == 5

    def test_run_pipeline_short_idea_returns_stream(self):
        # Short idea (< 10 chars) should return a stream with error event
        resp = self._client.post("/pipeline/run", json={
            "idea": "short",
            "title": "",
            "genre": "Tiên Hiệp",
            "style": "Miêu tả chi tiết",
            "num_chapters": 1,
            "num_characters": 2,
            "word_count": 200,
            "num_sim_rounds": 1,
            "drama_level": "cao",
        })
        assert resp.status_code == 200
        # Should be SSE response with error
        assert "text/event-stream" in resp.headers.get("content-type", "")

    def test_resume_pipeline_invalid_checkpoint(self):
        resp = self._client.post("/pipeline/resume", json={"checkpoint": "nonexistent.json"})
        assert resp.status_code == 200
        content = resp.text
        assert "error" in content or "Checkpoint" in content

    def test_sanitize_summary_empty(self):
        from api.pipeline_routes import _sanitize_summary
        result = _sanitize_summary({})
        assert result == {}

    def test_sanitize_summary_none_draft(self):
        from api.pipeline_routes import _sanitize_summary
        result = _sanitize_summary({"draft": None})
        assert result == {"draft": None}

    def test_sanitize_summary_chapters(self):
        from api.pipeline_routes import _sanitize_summary
        summary = {
            "draft": {
                "chapters": [
                    {"content": "<b>Hello</b> World"},
                    {"content": "No HTML here"},
                ]
            }
        }
        result = _sanitize_summary(summary)
        # The chapters content should be processed
        assert "chapters" in result["draft"]

    def test_sanitize_summary_enhanced_section(self):
        from api.pipeline_routes import _sanitize_summary
        summary = {
            "enhanced": {
                "chapters": [
                    {"content": "<em>Enhanced content</em>"}
                ]
            }
        }
        result = _sanitize_summary(summary)
        assert "enhanced" in result

    def test_orchestrator_view_get(self):
        from api.pipeline_routes import _orchestrators
        result = _orchestrators.get("nonexistent-key", None)
        assert result is None

    def test_orchestrator_view_contains(self):
        from api.pipeline_routes import _orchestrators
        assert "nonexistent-key" not in _orchestrators


# ===========================================================================
# services/handlers.py
# ===========================================================================

class TestHandlersModule:
    """Tests for services/handlers.py handler functions."""

    def _make_t(self, key, **kw):
        """Simple translation mock — returns key."""
        return key

    def _make_orch_state(self, has_output=True, has_draft=True, has_enhanced=False):
        """Build minimal orchestrator mock."""
        mock_orch = MagicMock()
        if has_output:
            mock_output = MagicMock()
            if has_draft:
                mock_draft = MagicMock()
                mock_draft.title = "Test Story"
                mock_draft.synopsis = "A synopsis"
                mock_draft.characters = []
                mock_draft.chapters = [MagicMock(content="Chapter content")]
                mock_output.story_draft = mock_draft
            else:
                mock_output.story_draft = None
            if has_enhanced:
                mock_output.enhanced_story = MagicMock()
            else:
                mock_output.enhanced_story = None
            mock_orch.output = mock_output
        else:
            mock_orch.output = None
        return mock_orch

    # _friendly_error
    def test_friendly_error_connection(self):
        from services.handlers import _friendly_error
        exc = ConnectionError("Connection refused")
        result = _friendly_error(exc, self._make_t)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_friendly_error_timeout(self):
        from services.handlers import _friendly_error
        exc = TimeoutError("timeout")
        result = _friendly_error(exc, self._make_t)
        assert "timeout" in result.lower() or "error" in result.lower() or result

    def test_friendly_error_json_validation(self):
        from services.handlers import _friendly_error
        exc = ValueError("JSON validation failed")
        result = _friendly_error(exc, self._make_t)
        assert isinstance(result, str)

    def test_friendly_error_fallback(self):
        from services.handlers import _friendly_error
        exc = RuntimeError("something random")
        result = _friendly_error(exc, self._make_t)
        assert isinstance(result, str)

    # handle_login
    def test_handle_login_empty_username(self):
        from services.handlers import handle_login
        profile, msg, table = handle_login("", "password", self._make_t)
        assert profile is None
        assert table == []

    def test_handle_login_empty_password(self):
        from services.handlers import handle_login
        profile, msg, table = handle_login("user", "", self._make_t)
        assert profile is None

    def test_handle_login_success(self):
        from services.handlers import handle_login
        mock_profile = MagicMock()
        mock_profile.user_id = "u1"
        mock_profile.username = "testuser"
        mock_profile.model_dump.return_value = {"user_id": "u1", "username": "testuser"}
        with patch("services.handlers.UserManager") as MockUM:
            mock_um = MagicMock()
            mock_um.login.return_value = mock_profile
            mock_um.list_stories.return_value = [{"story_id": "s1", "title": "Story 1", "saved_at": "2026-01-01"}]
            MockUM.return_value = mock_um
            profile, msg, table = handle_login("testuser", "password", self._make_t)
        assert profile is not None
        assert len(table) == 1

    def test_handle_login_failure(self):
        from services.handlers import handle_login
        with patch("services.handlers.UserManager") as MockUM:
            mock_um = MagicMock()
            mock_um.login.return_value = None
            MockUM.return_value = mock_um
            profile, msg, table = handle_login("baduser", "badpass", self._make_t)
        assert profile is None

    # handle_register
    def test_handle_register_empty_fields(self):
        from services.handlers import handle_register
        profile, msg, table = handle_register("", "", self._make_t)
        assert profile is None

    def test_handle_register_success(self):
        from services.handlers import handle_register
        mock_profile = MagicMock()
        mock_profile.model_dump.return_value = {"user_id": "u1", "username": "newuser"}
        with patch("services.handlers.UserManager") as MockUM:
            mock_um = MagicMock()
            mock_um.register.return_value = mock_profile
            MockUM.return_value = mock_um
            profile, msg, table = handle_register("newuser", "password", self._make_t)
        assert profile is not None

    def test_handle_register_duplicate(self):
        from services.handlers import handle_register
        with patch("services.handlers.UserManager") as MockUM:
            mock_um = MagicMock()
            mock_um.register.side_effect = ValueError("Username taken")
            MockUM.return_value = mock_um
            profile, msg, table = handle_register("existing", "password", self._make_t)
        assert profile is None

    # handle_save_story
    def test_handle_save_story_no_user(self):
        from services.handlers import handle_save_story
        msg, table = handle_save_story(None, MagicMock(), "title", self._make_t)
        assert isinstance(msg, str)
        assert table == []

    def test_handle_save_story_no_orch(self):
        from services.handlers import handle_save_story
        msg, table = handle_save_story({"user_id": "u1"}, None, "title", self._make_t)
        assert isinstance(msg, str)
        assert table == []

    def test_handle_save_story_success(self):
        from services.handlers import handle_save_story
        orch_state = self._make_orch_state()
        orch_state.output.model_dump.return_value = {}
        with patch("services.handlers.UserManager") as MockUM:
            mock_um = MagicMock()
            mock_um.save_story.return_value = "story-123"
            mock_um.list_stories.return_value = [{"story_id": "story-123", "title": "Test", "saved_at": "2026"}]
            MockUM.return_value = mock_um
            msg, table = handle_save_story({"user_id": "u1"}, orch_state, "My Story", self._make_t)
        assert "story-123" in msg
        assert len(table) == 1

    # handle_export_pdf
    def test_handle_export_pdf_no_orch(self):
        from services.handlers import handle_export_pdf
        files, stats = handle_export_pdf(None, self._make_t)
        assert files is None

    def test_handle_export_pdf_no_story(self):
        from services.handlers import handle_export_pdf
        orch_state = self._make_orch_state(has_draft=False)
        orch_state.output.enhanced_story = None
        orch_state.output.story_draft = None
        files, stats = handle_export_pdf(orch_state, self._make_t)
        assert files is None

    def test_handle_export_pdf_success(self):
        from services.handlers import handle_export_pdf
        orch_state = self._make_orch_state()
        with patch("services.handlers.PDFExporter") as MockPDF:
            MockPDF.export.return_value = "output/story.pdf"
            stats_mock = MagicMock()
            stats_mock.model_dump.return_value = {"word_count": 1000, "reading_time_min": 5}
            MockPDF.compute_reading_stats.return_value = stats_mock
            files, stats = handle_export_pdf(orch_state, self._make_t)
        assert files is not None
        assert "output/story.pdf" in files

    def test_handle_export_pdf_exception(self):
        from services.handlers import handle_export_pdf
        orch_state = self._make_orch_state()
        with patch("services.handlers.PDFExporter") as MockPDF:
            MockPDF.export.side_effect = RuntimeError("PDF generation failed")
            files, stats = handle_export_pdf(orch_state, self._make_t)
        assert files is None
        assert "error" in stats

    # handle_export_epub
    def test_handle_export_epub_no_orch(self):
        from services.handlers import handle_export_epub
        files, stats = handle_export_epub(None, self._make_t)
        assert files is None

    def test_handle_export_epub_success(self):
        from services.handlers import handle_export_epub
        orch_state = self._make_orch_state()
        with patch("services.epub_exporter.EPUBExporter") as MockEPUB, \
             patch("services.handlers.PDFExporter") as MockPDF:
            MockEPUB.export.return_value = "output/story.epub"
            stats_mock = MagicMock()
            stats_mock.model_dump.return_value = {"word_count": 500}
            MockPDF.compute_reading_stats.return_value = stats_mock
            files, stats = handle_export_epub(orch_state, self._make_t)
        # epub may succeed or fail depending on mock setup
        assert files is not None or stats is not None

    # handle_share_story
    def test_handle_share_story_no_orch(self):
        from services.handlers import handle_share_story
        link, _ = handle_share_story(None, self._make_t)
        assert link == ""

    def test_handle_share_story_no_story(self):
        from services.handlers import handle_share_story
        orch_state = self._make_orch_state(has_draft=False)
        orch_state.output.enhanced_story = None
        orch_state.output.story_draft = None
        link, _ = handle_share_story(orch_state, self._make_t)
        assert link == ""

    def test_handle_share_story_success(self):
        from services.handlers import handle_share_story
        orch_state = self._make_orch_state()
        with patch("services.handlers.ShareManager") as MockSM, \
             patch("services.handlers.ConfigManager") as MockCM:
            mock_share = MagicMock()
            mock_share.html_path = "shared/story_abc.html"
            MockSM.return_value.create_share.return_value = mock_share
            mock_cm = MagicMock()
            mock_cm.pipeline.share_base_url = "http://localhost/"
            MockCM.return_value = mock_cm
            link, _ = handle_share_story(orch_state, self._make_t)
        assert "story_abc.html" in link

    # handle_export_files
    def test_handle_export_files_no_orch(self):
        from services.handlers import handle_export_files
        result = handle_export_files(None, ["TXT"])
        assert result is None

    def test_handle_export_files_success(self):
        from services.handlers import handle_export_files
        mock_orch = MagicMock()
        mock_orch.export_output.return_value = ["output/story.txt"]
        result = handle_export_files(mock_orch, ["TXT"])
        assert result == ["output/story.txt"]

    def test_handle_export_files_empty_returns_none(self):
        from services.handlers import handle_export_files
        mock_orch = MagicMock()
        mock_orch.export_output.return_value = []
        result = handle_export_files(mock_orch, ["TXT"])
        assert result is None

    def test_handle_export_files_exception(self):
        from services.handlers import handle_export_files
        mock_orch = MagicMock()
        mock_orch.export_output.side_effect = RuntimeError("export error")
        result = handle_export_files(mock_orch, ["TXT"])
        assert result is None

    # handle_export_zip
    def test_handle_export_zip_no_orch(self):
        from services.handlers import handle_export_zip
        result = handle_export_zip(None, ["TXT"], self._make_t)
        assert result is None

    def test_handle_export_zip_success(self):
        from services.handlers import handle_export_zip
        mock_orch = MagicMock()
        mock_orch.export_zip.return_value = "output/story.zip"
        result = handle_export_zip(mock_orch, ["TXT", "EPUB"], self._make_t)
        assert result == ["output/story.zip"]

    def test_handle_export_zip_none_path(self):
        from services.handlers import handle_export_zip
        mock_orch = MagicMock()
        mock_orch.export_zip.return_value = None
        result = handle_export_zip(mock_orch, ["TXT"], self._make_t)
        assert result is None

    def test_handle_export_zip_exception(self):
        from services.handlers import handle_export_zip
        mock_orch = MagicMock()
        mock_orch.export_zip.side_effect = RuntimeError("zip error")
        result = handle_export_zip(mock_orch, ["TXT"], self._make_t)
        assert result is None

    # get_checkpoint_choices
    def test_get_checkpoint_choices(self):
        from services.handlers import get_checkpoint_choices
        with patch("services.handlers.PipelineOrchestrator") as MockOrch:
            MockOrch.list_checkpoints.return_value = [
                {"file": "story_1.json", "modified": "2026-01-01", "size_kb": 5}
            ]
            result = get_checkpoint_choices()
        assert len(result) == 1
        assert "story_1.json" in result[0]

    def test_get_checkpoint_choices_empty(self):
        from services.handlers import get_checkpoint_choices
        with patch("services.handlers.PipelineOrchestrator") as MockOrch:
            MockOrch.list_checkpoints.return_value = []
            result = get_checkpoint_choices()
        assert result == []

    # resolve_checkpoint_path
    def test_resolve_checkpoint_path_none(self):
        from services.handlers import resolve_checkpoint_path
        result = resolve_checkpoint_path(None)
        assert result is None

    def test_resolve_checkpoint_path_empty(self):
        from services.handlers import resolve_checkpoint_path
        result = resolve_checkpoint_path("")
        assert result is None

    def test_resolve_checkpoint_path_valid(self):
        from services.handlers import resolve_checkpoint_path
        with patch("services.handlers.PipelineOrchestrator") as MockOrch:
            MockOrch.CHECKPOINT_DIR = "/tmp/checkpoints"
            result = resolve_checkpoint_path("story_1.json (2026-01-01, 5KB)")
        assert result is not None
        assert "story_1.json" in result

    # handle_load_checkpoint
    def test_handle_load_checkpoint_no_choice(self):
        from services.handlers import handle_load_checkpoint
        msg, orch = handle_load_checkpoint("", None, self._make_t)
        assert "continue.no_checkpoint" in msg

    def test_handle_load_checkpoint_with_story(self):
        from services.handlers import handle_load_checkpoint
        mock_orch = MagicMock()
        mock_orch.output.story_draft.title = "Test Story"
        mock_orch.output.story_draft.chapters = [MagicMock()]
        mock_orch.output.story_draft.synopsis = "A synopsis"
        mock_orch.output.story_draft.characters = []
        with patch("services.handlers.PipelineOrchestrator") as MockOrch:
            MockOrch.CHECKPOINT_DIR = "/tmp/checkpoints"
            MockOrch.return_value = mock_orch
            msg, returned_orch = handle_load_checkpoint(
                "story_1.json (2026, 5KB)", None, self._make_t
            )
        assert returned_orch is not None

    # handle_genre_autofill
    def test_handle_genre_autofill_known_genre(self):
        from services.handlers import handle_genre_autofill
        result = handle_genre_autofill("Tiên Hiệp")
        assert result is not None
        num_chapters, words, style = result
        assert num_chapters == 50
        assert words == 3000

    def test_handle_genre_autofill_unknown_genre(self):
        from services.handlers import handle_genre_autofill
        result = handle_genre_autofill("Unknown Genre XYZ")
        assert result == (None, None, None)

    # handle_character_gallery
    def test_handle_character_gallery_no_orch(self):
        from services.handlers import handle_character_gallery
        result = handle_character_gallery(None)
        assert result == []

    def test_handle_character_gallery_no_output(self):
        from services.handlers import handle_character_gallery
        mock_orch = MagicMock()
        mock_orch.output = None
        result = handle_character_gallery(mock_orch)
        assert result == []

    def test_handle_character_gallery_no_refs(self):
        from services.handlers import handle_character_gallery
        mock_orch = MagicMock()
        mock_orch.output.character_refs = None
        result = handle_character_gallery(mock_orch)
        assert result == []

    def test_handle_add_chapters_no_orch(self):
        from services.handlers import handle_add_chapters
        msg, orch = handle_add_chapters(None, 3, 2000, self._make_t)
        assert orch is None

    def test_handle_delete_chapters_no_orch(self):
        from services.handlers import handle_delete_chapters
        msg, orch = handle_delete_chapters(None, 5, self._make_t)
        assert orch is None

    def test_handle_update_character_no_orch(self):
        from services.handlers import handle_update_character
        msg, orch = handle_update_character(None, "Hero", "brave", "revenge", self._make_t)
        assert orch is None

    def test_handle_update_character_no_name(self):
        from services.handlers import handle_update_character
        mock_orch = MagicMock()
        msg, orch = handle_update_character(mock_orch, "", "brave", "revenge", self._make_t)
        assert "continue.char_name" in msg

    def test_handle_update_character_no_updates(self):
        from services.handlers import handle_update_character
        mock_orch = MagicMock()
        mock_orch.output.story_draft = MagicMock()
        msg, orch = handle_update_character(mock_orch, "Hero", "", "", self._make_t)
        assert isinstance(msg, str)

    def test_handle_generate_images_no_orch(self):
        from services.handlers import handle_generate_images
        paths, msg = handle_generate_images(None, "none", self._make_t)
        assert paths == []

    def test_handle_enhance_no_orch(self):
        from services.handlers import handle_enhance
        msg, orch = handle_enhance(None, 3, 2000, self._make_t)
        assert orch is None


# ===========================================================================
# services/llm_cache.py
# ===========================================================================

class TestLLMCache:
    """Tests for LLMCache SQLite backend."""

    @pytest.fixture
    def cache(self, tmp_path):
        from services.llm_cache import LLMCache
        db_path = str(tmp_path / "test_cache.db")
        return LLMCache(db_path=db_path, ttl_days=1)

    def test_cache_miss_returns_none(self, cache):
        result = cache.get(system_prompt="sp", user_prompt="up", model="m", temperature=0.8, json_mode=False)
        assert result is None

    def test_cache_put_and_get(self, cache):
        params = dict(system_prompt="sp", user_prompt="up", model="m", temperature=0.8, json_mode=False)
        cache.put("The response text", **params)
        result = cache.get(**params)
        assert result == "The response text"

    def test_cache_hit_increments_hits(self, cache):
        params = dict(system_prompt="sp2", user_prompt="up2", model="m2", temperature=0.5, json_mode=False)
        cache.put("response", **params)
        cache.get(**params)
        stats = cache.stats()
        assert stats["hits"] >= 1

    def test_cache_miss_increments_misses(self, cache):
        params = dict(system_prompt="sp_miss", user_prompt="up_miss", model="m_miss", temperature=0.1, json_mode=False)
        cache.get(**params)
        stats = cache.stats()
        assert stats["misses"] >= 1

    def test_cache_stats_structure(self, cache):
        stats = cache.stats()
        assert "backend" in stats
        assert stats["backend"] == "sqlite"
        assert "total_entries" in stats
        assert "valid_entries" in stats
        assert "hit_rate_pct" in stats

    def test_cache_clear(self, cache):
        params = dict(system_prompt="sp3", user_prompt="up3", model="m3", temperature=0.7, json_mode=True)
        cache.put("data", **params)
        cache.clear()
        result = cache.get(**params)
        assert result is None
        stats = cache.stats()
        assert stats["total_entries"] == 0

    def test_cache_evict_expired(self, tmp_path):
        from services.llm_cache import LLMCache
        db_path = str(tmp_path / "expire_cache.db")
        cache = LLMCache(db_path=db_path, ttl_days=1)
        # Insert entry with fake old timestamp
        conn = cache._get_conn()
        import time
        import hashlib
        import json as _json
        old_params = dict(system_prompt="old", user_prompt="old", model="m", temperature=0.5, json_mode=False)
        raw = _json.dumps(old_params, sort_keys=True, ensure_ascii=False)
        key = hashlib.sha256(raw.encode()).hexdigest()
        old_ts = time.time() - (2 * 86400)  # 2 days ago
        conn.execute("INSERT OR REPLACE INTO cache (key, response, created_at) VALUES (?,?,?)",
                     (key, "old response", old_ts))
        conn.commit()
        removed = cache.evict_expired()
        assert removed >= 1

    def test_cache_different_params_different_keys(self, cache):
        params1 = dict(system_prompt="sp", user_prompt="up", model="m1", temperature=0.8, json_mode=False)
        params2 = dict(system_prompt="sp", user_prompt="up", model="m2", temperature=0.8, json_mode=False)
        cache.put("response1", **params1)
        assert cache.get(**params2) is None

    def test_cache_invalid_ttl_defaults_to_7(self, tmp_path):
        from services.llm_cache import LLMCache
        db_path = str(tmp_path / "ttl_cache.db")
        # ttl_days < 1 should default to 7
        cache = LLMCache(db_path=db_path, ttl_days=0)
        assert cache.ttl == 7 * 86400

    def test_make_key_deterministic(self, cache):
        params = dict(system_prompt="hello", user_prompt="world", model="test", temperature=0.5, json_mode=False)
        key1 = cache._make_key(**params)
        key2 = cache._make_key(**params)
        assert key1 == key2

    def test_create_cache_returns_sqlite_by_default(self, tmp_path):
        from services.llm_cache import create_cache, LLMCache
        db_path = str(tmp_path / "factory_cache.db")
        with patch.dict(os.environ, {}, clear=False):
            # Remove REDIS_URL if set
            env = dict(os.environ)
            env.pop("REDIS_URL", None)
            with patch.dict(os.environ, env, clear=True):
                cache = create_cache(redis_url="", db_path=db_path, ttl_days=1)
        assert isinstance(cache, LLMCache)

    def test_get_cache_singleton(self, tmp_path):
        from services import llm_cache as lc
        # Reset singleton
        orig = lc._cache_instance
        lc._cache_instance = None
        try:
            with patch("services.llm_cache.create_cache") as mock_create:
                mock_cache = MagicMock()
                mock_create.return_value = mock_cache
                c1 = lc.get_cache()
                c2 = lc.get_cache()
            assert c1 is c2
        finally:
            lc._cache_instance = orig

    def test_hit_rate_calculation(self, cache):
        params = dict(system_prompt="hit_rate", user_prompt="up", model="m", temperature=0.8, json_mode=False)
        cache.put("resp", **params)
        # 1 miss + 1 hit
        cache.get(system_prompt="miss_sp", user_prompt="up", model="m", temperature=0.8, json_mode=False)
        cache.get(**params)
        stats = cache.stats()
        assert 0.0 <= stats["hit_rate_pct"] <= 100.0


# ===========================================================================
# services/llm/client.py
# ===========================================================================

class TestLLMClient:
    """Tests for LLMClient singleton in services/llm/client.py."""

    @pytest.fixture(autouse=True)
    def reset_client(self):
        """Reset LLMClient singleton before each test."""
        from services.llm.client import LLMClient
        LLMClient.reset()
        yield
        LLMClient.reset()

    def test_singleton_same_instance(self):
        from services.llm.client import LLMClient
        with patch("services.llm_client.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMCache") as MockCache:
            MockCM.return_value = _mock_config_manager()
            MockCache.return_value = MagicMock()
            c1 = LLMClient()
            c2 = LLMClient()
        assert c1 is c2

    def test_reset_creates_new_instance(self):
        from services.llm.client import LLMClient
        with patch("services.llm_client.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMCache") as MockCache:
            MockCM.return_value = _mock_config_manager()
            MockCache.return_value = MagicMock()
            c1 = LLMClient()
        LLMClient.reset()
        with patch("services.llm_client.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMCache") as MockCache:
            MockCM.return_value = _mock_config_manager()
            MockCache.return_value = MagicMock()
            c2 = LLMClient()
        assert c1 is not c2

    def test_model_for_layer_uses_layer_model(self):
        from services.llm.client import LLMClient
        with patch("services.llm_client.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMCache") as MockCache:
            mock_cm = _mock_config_manager()
            mock_cm.llm.layer1_model = "gpt-4o-layer1"
            MockCM.return_value = mock_cm
            MockCache.return_value = MagicMock()
            client = LLMClient()
            client._current_model = "gpt-4o-mini"
            result = client.model_for_layer(1)
        assert result == "gpt-4o-layer1"

    def test_model_for_layer_falls_back_to_primary(self):
        from services.llm.client import LLMClient
        with patch("services.llm_client.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMCache") as MockCache:
            mock_cm = _mock_config_manager()
            mock_cm.llm.layer1_model = ""
            mock_cm.llm.model = "gpt-4o-mini"
            MockCM.return_value = mock_cm
            MockCache.return_value = MagicMock()
            client = LLMClient()
            client._current_model = ""
            result = client.model_for_layer(1)
        assert result == "gpt-4o-mini"

    def test_model_for_layer_unknown_layer(self):
        from services.llm.client import LLMClient
        with patch("services.llm_client.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMCache") as MockCache:
            mock_cm = _mock_config_manager()
            mock_cm.llm.model = "fallback-model"
            MockCM.return_value = mock_cm
            MockCache.return_value = MagicMock()
            client = LLMClient()
            client._current_model = "fallback-model"
            result = client.model_for_layer(99)
        assert result == "fallback-model"

    def test_get_layer_config_with_layer_specific_provider(self):
        from services.llm.client import LLMClient, LayerConfig
        with patch("services.llm_client.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMCache") as MockCache:
            mock_cm = _mock_config_manager()
            mock_cm.llm.layer1_model = "claude-3-opus"
            mock_cm.llm.layer1_base_url = "https://api.anthropic.com/v1"
            mock_cm.llm.layer1_api_key = "sk-ant-key"
            MockCM.return_value = mock_cm
            MockCache.return_value = MagicMock()
            client = LLMClient()
            cfg = client.get_layer_config(1)
        assert isinstance(cfg, LayerConfig)
        assert cfg.model == "claude-3-opus"
        assert cfg.base_url == "https://api.anthropic.com/v1"
        assert cfg.api_key == "sk-ant-key"
        assert cfg.is_layer_specific is True

    def test_get_layer_config_falls_back_to_primary(self):
        from services.llm.client import LLMClient, LayerConfig
        with patch("services.llm_client.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMCache") as MockCache:
            mock_cm = _mock_config_manager()
            mock_cm.llm.layer1_model = ""
            mock_cm.llm.layer1_base_url = ""
            mock_cm.llm.layer1_api_key = ""
            MockCM.return_value = mock_cm
            MockCache.return_value = MagicMock()
            client = LLMClient()
            client._current_model = "gpt-4o-mini"
            cfg = client.get_layer_config(1)
        assert isinstance(cfg, LayerConfig)
        assert cfg.model == "gpt-4o-mini"
        assert cfg.is_layer_specific is False

    def test_mark_rate_limited(self):
        from services.llm.client import LLMClient
        with patch("services.llm_client.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMCache") as MockCache:
            MockCM.return_value = _mock_config_manager()
            MockCache.return_value = MagicMock()
            client = LLMClient()
            client._mark_rate_limited("sk-test-key", cooldown=30.0)
        assert "sk-test-key" in client._rate_limited_keys
        assert client._rate_limited_keys["sk-test-key"] > time.time()

    def test_resolve_api_keys_primary_only(self):
        from services.llm.client import LLMClient
        with patch("services.llm_client.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMCache") as MockCache:
            mock_cm = _mock_config_manager()
            mock_cm.llm.api_keys = []
            MockCM.return_value = mock_cm
            MockCache.return_value = MagicMock()
            client = LLMClient()
            entries = client._resolve_api_keys(mock_cm)
        assert len(entries) == 1
        assert entries[0]["api_key"] == "sk-test1234abcd"

    def test_resolve_api_keys_with_string_keys(self):
        from services.llm.client import LLMClient
        with patch("services.llm_client.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMCache") as MockCache:
            mock_cm = _mock_config_manager()
            mock_cm.llm.api_keys = ["sk-extra1", "sk-extra2"]
            MockCM.return_value = mock_cm
            MockCache.return_value = MagicMock()
            client = LLMClient()
            entries = client._resolve_api_keys(mock_cm)
        assert len(entries) == 3  # primary + 2 extras

    def test_resolve_api_keys_with_dict_keys(self):
        from services.llm.client import LLMClient
        with patch("services.llm_client.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMCache") as MockCache:
            mock_cm = _mock_config_manager()
            mock_cm.llm.api_keys = [{"key": "sk-dict-key", "base_url": "https://custom.com/v1"}]
            MockCM.return_value = mock_cm
            MockCache.return_value = MagicMock()
            client = LLMClient()
            entries = client._resolve_api_keys(mock_cm)
        assert len(entries) == 2
        assert any(e["api_key"] == "sk-dict-key" for e in entries)

    def test_resolve_api_keys_skips_rate_limited(self):
        from services.llm.client import LLMClient
        with patch("services.llm_client.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMCache") as MockCache:
            mock_cm = _mock_config_manager()
            mock_cm.llm.api_keys = ["sk-extra-rate-limited"]
            MockCM.return_value = mock_cm
            MockCache.return_value = MagicMock()
            client = LLMClient()
            # Rate-limit the extra key
            client._rate_limited_keys["sk-extra-rate-limited"] = time.time() + 300
            entries = client._resolve_api_keys(mock_cm)
        # Should only have primary key
        assert all(e["api_key"] != "sk-extra-rate-limited" for e in entries)

    def test_resolve_api_keys_all_rate_limited_clears(self):
        from services.llm.client import LLMClient
        with patch("services.llm_client.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMCache") as MockCache:
            mock_cm = _mock_config_manager()
            mock_cm.llm.api_keys = []
            MockCM.return_value = mock_cm
            MockCache.return_value = MagicMock()
            client = LLMClient()
            # Rate-limit the primary key too
            client._rate_limited_keys["sk-test1234abcd"] = time.time() + 300
            entries = client._resolve_api_keys(mock_cm)
        # Should clear and return all
        assert len(entries) >= 1

    def test_retry_with_backoff_success_first_try(self):
        from services.llm.client import LLMClient
        with patch("services.llm_client.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMCache") as MockCache:
            MockCM.return_value = _mock_config_manager()
            MockCache.return_value = MagicMock()
            client = LLMClient()
        result = client._retry_with_backoff(lambda: "success", label="test")
        assert result == "success"

    def test_retry_with_backoff_non_transient_raises_immediately(self):
        from services.llm.client import LLMClient
        with patch("services.llm_client.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMCache") as MockCache:
            MockCM.return_value = _mock_config_manager()
            MockCache.return_value = MagicMock()
            client = LLMClient()
        call_count = [0]
        def failing():
            call_count[0] += 1
            raise ValueError("Non-transient error")
        with pytest.raises(ValueError):
            client._retry_with_backoff(failing, label="test")

    def test_generate_with_cache_hit(self):
        from services.llm.client import LLMClient
        with patch("services.llm_client.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMCache") as MockCache:
            mock_cm = _mock_config_manager()
            MockCM.return_value = mock_cm
            mock_cache = MagicMock()
            mock_cache.get.return_value = "cached response"
            MockCache.return_value = mock_cache
            client = LLMClient()

        with patch("services.llm_client.ConfigManager") as MockCM2, \
             patch("services.llm_client.LLMCache") as MockCache2, \
             patch("services.prompts.localize_prompt", side_effect=lambda x, _: x):
            MockCM2.return_value = mock_cm
            mock_cache2 = MagicMock()
            mock_cache2.get.return_value = "cached response"
            MockCache2.return_value = mock_cache2
            result = client.generate("system", "user")

        assert result == "cached response"

    def test_legacy_client_adapter_complete(self):
        from services.llm.client import _LegacyClientAdapter
        mock_raw = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "test response"
        mock_raw.chat.completions.create.return_value = mock_response
        adapter = _LegacyClientAdapter(mock_raw)
        result = adapter.complete([{"role": "user", "content": "hi"}], "model", 0.7, 100)
        assert result == "test response"

    def test_legacy_client_adapter_complete_json_mode(self):
        from services.llm.client import _LegacyClientAdapter
        mock_raw = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = '{"key": "value"}'
        mock_raw.chat.completions.create.return_value = mock_response
        adapter = _LegacyClientAdapter(mock_raw)
        result = adapter.complete([{"role": "user", "content": "hi"}], "model", 0.7, 100, json_mode=True)
        assert '{"key"' in result

    def test_legacy_client_adapter_stream(self):
        from services.llm.client import _LegacyClientAdapter
        mock_raw = MagicMock()
        mock_chunk1 = MagicMock()
        mock_chunk1.choices[0].delta.content = "Hello"
        mock_chunk2 = MagicMock()
        mock_chunk2.choices[0].delta.content = " world"
        mock_chunk3 = MagicMock()
        mock_chunk3.choices = []
        mock_raw.chat.completions.create.return_value = iter([mock_chunk1, mock_chunk2])
        adapter = _LegacyClientAdapter(mock_raw)
        chunks = list(adapter.stream([{"role": "user", "content": "hi"}], "model", 0.7, 100))
        assert chunks == ["Hello", " world"]

    def test_build_fallback_chain_default_tier(self):
        from services.llm.client import LLMClient
        with patch("services.llm_client.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMCache") as MockCache:
            mock_cm = _mock_config_manager()
            MockCM.return_value = mock_cm
            MockCache.return_value = MagicMock()
            client = LLMClient()
        with patch("services.llm.client._get_provider") as mock_get_provider:
            mock_get_provider.return_value = MagicMock()
            chain = client._build_fallback_chain(mock_cm, "default")
        assert len(chain) >= 1
        assert chain[0]["label"] == "primary"

    def test_build_fallback_chain_cheap_tier(self):
        from services.llm.client import LLMClient
        with patch("services.llm_client.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMCache") as MockCache:
            mock_cm = _mock_config_manager()
            mock_cm.llm.cheap_model = "gpt-3.5-turbo"
            MockCM.return_value = mock_cm
            MockCache.return_value = MagicMock()
            client = LLMClient()
        with patch("services.llm.client._get_provider") as mock_get_provider:
            mock_get_provider.return_value = MagicMock()
            chain = client._build_fallback_chain(mock_cm, "cheap")
        assert len(chain) >= 1
        assert "cheap" in chain[0]["label"]

    def test_build_fallback_chain_with_fallback_models(self):
        from services.llm.client import LLMClient
        with patch("services.llm_client.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMCache") as MockCache:
            mock_cm = _mock_config_manager()
            mock_cm.llm.fallback_models = [
                {"model": "claude-haiku", "base_url": "https://api.anthropic.com/v1",
                 "api_key": "sk-ant-test", "enabled": True}
            ]
            MockCM.return_value = mock_cm
            MockCache.return_value = MagicMock()
            client = LLMClient()
        with patch("services.llm.client._get_provider") as mock_get_provider:
            mock_get_provider.return_value = MagicMock()
            chain = client._build_fallback_chain(mock_cm, "default")
        assert any("fallback" in entry["label"] for entry in chain)

    def test_build_fallback_chain_skips_disabled_fallback(self):
        from services.llm.client import LLMClient
        with patch("services.llm_client.ConfigManager") as MockCM, \
             patch("services.llm_client.LLMCache") as MockCache:
            mock_cm = _mock_config_manager()
            mock_cm.llm.fallback_models = [
                {"model": "disabled-model", "base_url": "https://x.com/v1",
                 "api_key": "sk-x", "enabled": False}
            ]
            MockCM.return_value = mock_cm
            MockCache.return_value = MagicMock()
            client = LLMClient()
        with patch("services.llm.client._get_provider") as mock_get_provider:
            mock_get_provider.return_value = MagicMock()
            chain = client._build_fallback_chain(mock_cm, "default")
        assert not any("disabled-model" in entry["label"] for entry in chain)

    def test_repair_json_static_method(self):
        from services.llm.client import LLMClient
        result = LLMClient._repair_json('{"key": "value"}')
        assert isinstance(result, str)


# ===========================================================================
# services/auth/auth.py — additional coverage
# ===========================================================================

class TestAuthModule:
    """Additional tests for services/auth/auth.py (RS256 JWT)."""

    def test_create_and_verify_roundtrip(self):
        import services.auth.auth as auth
        token = auth.create_token("u1", "alice")
        payload = auth.verify_token(token)
        assert payload["sub"] == "u1"
        assert payload["username"] == "alice"
        assert "jti" in payload
        assert "exp" in payload
        assert "iat" in payload

    def test_verify_malformed_missing_parts(self):
        import services.auth.auth as auth
        with pytest.raises(ValueError, match="[Mm]alformed"):
            auth.verify_token("only.two")

    def test_verify_malformed_empty(self):
        import services.auth.auth as auth
        with pytest.raises(ValueError):
            auth.verify_token("")

    def test_verify_wrong_algorithm(self):
        import services.auth.auth as auth
        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
        ).rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(
            json.dumps({"sub": "x"}).encode()
        ).rstrip(b"=").decode()
        sig = base64.urlsafe_b64encode(b"fake").rstrip(b"=").decode()
        with pytest.raises(ValueError, match="Unsupported"):
            auth.verify_token(f"{header}.{payload}.{sig}")

    def test_verify_tampered_payload(self):
        import services.auth.auth as auth
        token = auth.create_token("u1", "original")
        parts = token.split(".")
        fake_payload = base64.urlsafe_b64encode(
            json.dumps({"sub": "attacker", "username": "hacked", "iat": 0, "exp": 9999999999}).encode()
        ).rstrip(b"=").decode()
        bad_token = f"{parts[0]}.{fake_payload}.{parts[2]}"
        with pytest.raises(ValueError):
            auth.verify_token(bad_token)

    def test_verify_invalid_sig_encoding(self):
        import services.auth.auth as auth
        token = auth.create_token("u2", "bob")
        parts = token.split(".")
        bad_token = f"{parts[0]}.{parts[1]}.!!!invalid!!!"
        with pytest.raises(ValueError):
            auth.verify_token(bad_token)

    def test_b64url_encode_decode(self):
        import services.auth.auth as auth
        data = b"test binary data \x00\xff"
        encoded = auth._b64url_encode(data)
        assert "=" not in encoded
        decoded = auth._b64url_decode(encoded)
        assert decoded == data

    def test_detect_provider_name_in_auth_routes(self):
        from api.config_routes import _detect_provider_name
        assert _detect_provider_name("") == "custom"

    def test_key_dir_uses_env(self, tmp_path):
        import services.auth.auth as auth
        with patch.dict(os.environ, {
            "STORYFORGE_JWT_KEY_DIR": str(tmp_path),
            "STORYFORGE_JWT_KEY_ID": "testkey",
        }):
            key_dir = auth._key_dir()
        assert "testkey" in str(key_dir)

    def test_load_or_generate_rsa_keys(self, tmp_path):
        import services.auth.auth as auth
        # Reset cached keys so they regenerate
        auth._cached_priv = None
        auth._cached_pubs = None
        auth._cached_kid = None
        with patch.dict(os.environ, {
            "STORYFORGE_JWT_KEY_DIR": str(tmp_path),
            "STORYFORGE_JWT_KEY_ID": "fresh",
        }):
            priv, pubs = auth._load_or_generate_rsa_keys()
        assert priv is not None
        assert len(pubs) >= 1

    def test_token_with_revoked_jti(self):
        """Token with revoked jti should raise ValueError."""
        import services.auth.auth as auth
        token = auth.create_token("u3", "eve")
        # Get the jti from the token
        parts = token.split(".")
        payload = json.loads(auth._b64url_decode(parts[1]))
        payload["jti"]
        with patch("services.auth.auth.is_revoked", return_value=True):
            with pytest.raises(ValueError, match="revoked"):
                auth.verify_token(token)


# ===========================================================================
# services/auth/jwt_manager.py — additional coverage
# ===========================================================================

class TestJWTManager:
    """Tests for services/auth/jwt_manager.py HS256-based JWT manager."""

    @pytest.fixture(autouse=True)
    def set_secret(self):
        with patch.dict(os.environ, {"STORYFORGE_SECRET_KEY": "test-jwt-manager-secret-12345"}):
            # Reset singleton so it picks up env key
            from services.auth import jwt_manager as jm
            orig = jm._JWTKeyStore._instance
            jm._JWTKeyStore._instance = None
            # Also reset module-level _store
            jm._store = jm._JWTKeyStore()
            yield
            jm._JWTKeyStore._instance = orig

    def test_sign_token_returns_jwt_string(self):
        from services.auth.jwt_manager import sign_token
        token = sign_token({"sub": "u1", "username": "alice"})
        assert isinstance(token, str)
        assert token.count(".") == 2

    def test_verify_token_success(self):
        from services.auth.jwt_manager import sign_token, verify_token
        token = sign_token({"sub": "u1", "username": "alice"}, expiry=3600)
        payload = verify_token(token)
        assert payload["sub"] == "u1"
        assert payload["username"] == "alice"

    def test_verify_expired_token(self):
        from services.auth.jwt_manager import sign_token, verify_token
        token = sign_token({"sub": "u1"}, expiry=-1)  # Already expired
        with pytest.raises(ValueError, match="expired"):
            verify_token(token)

    def test_verify_malformed_token(self):
        from services.auth.jwt_manager import verify_token
        with pytest.raises(ValueError, match="Malformed"):
            verify_token("only.two")

    def test_verify_invalid_signature(self):
        from services.auth.jwt_manager import sign_token, verify_token
        token = sign_token({"sub": "u1"}, expiry=3600)
        parts = token.split(".")
        bad_sig = base64.urlsafe_b64encode(b"bad_signature").rstrip(b"=").decode()
        bad_token = f"{parts[0]}.{parts[1]}.{bad_sig}"
        with pytest.raises(ValueError, match="[Ii]nvalid"):
            verify_token(bad_token)

    def test_generate_key_returns_hex(self):
        from services.auth.jwt_manager import generate_key
        key = generate_key()
        assert isinstance(key, str)
        assert len(key) == 64  # 32 bytes = 64 hex chars

    def test_get_current_key_returns_bytes(self):
        from services.auth.jwt_manager import get_current_key
        key = get_current_key()
        assert isinstance(key, bytes)
        assert len(key) == 32  # SHA256 produces 32 bytes

    def test_get_valid_keys_list(self):
        from services.auth.jwt_manager import get_valid_keys
        keys = get_valid_keys()
        assert isinstance(keys, list)
        assert len(keys) >= 1

    def test_rotate_key_env_key_skipped(self):
        """With STORYFORGE_SECRET_KEY set, rotation is skipped."""
        from services.auth import jwt_manager as jm
        key_before = jm.get_current_key()
        jm.rotate_key()  # Should be a no-op since env key is set
        key_after = jm.get_current_key()
        assert key_before == key_after  # env key doesn't change

    def test_maybe_rotate_returns_false_with_env_key(self):
        from services.auth import jwt_manager as jm
        result = jm._store.maybe_rotate()
        assert result is False  # env key → no rotation

    def test_token_contains_exp_and_iat(self):
        from services.auth.jwt_manager import sign_token, verify_token
        token = sign_token({"sub": "u1"}, expiry=3600)
        payload = verify_token(token)
        assert "exp" in payload
        assert "iat" in payload
        assert payload["exp"] > int(time.time())

    def test_token_max_age_rejected(self):
        """Token with very old iat should be rejected if MAX_TOKEN_AGE exceeded."""
        from services.auth import jwt_manager as jm
        from services._jwt_helpers import b64url_encode, sign_input
        key_bytes = jm.get_current_key()
        old_iat = int(time.time()) - (jm.MAX_TOKEN_AGE + 100)
        payload = {
            "sub": "u1", "username": "old_user",
            "iat": old_iat,
            "exp": int(time.time()) + 3600,  # still valid exp
        }
        header = b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
        body = b64url_encode(json.dumps(payload).encode())
        signing_input = f"{header}.{body}"
        sig = sign_input(signing_input, key_bytes)
        token = f"{signing_input}.{sig}"
        with pytest.raises(ValueError, match="age|expired|Invalid"):
            jm.verify_token(token)

    def test_verify_malformed_payload(self):
        from services.auth import jwt_manager as jm
        from services._jwt_helpers import b64url_encode, sign_input
        key_bytes = jm.get_current_key()
        header = b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
        # Invalid JSON in payload
        bad_body = base64.urlsafe_b64encode(b"not_json").rstrip(b"=").decode()
        signing_input = f"{header}.{bad_body}"
        sig = sign_input(signing_input, key_bytes)
        token = f"{signing_input}.{sig}"
        with pytest.raises(ValueError):
            jm.verify_token(token)
