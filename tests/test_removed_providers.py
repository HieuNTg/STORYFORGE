"""The web-session providers are gone: FlowKit, qwen-local, Codex image, Gemini Web.

They each automated a consumer web session (Google Labs through a Chrome
extension, chat.qwen.ai through a proxy, the ChatGPT backend through the Codex
CLI login, the Gemini/Qwen web apps through a browser bridge). These tests pin
the removal and the upgrade path for a contributor's old ``data/config.json``.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import ConfigManager, LLMConfig, PipelineConfig
from config import persistence
from config.persistence import load_config, save_config


_OLD_CONFIG = {
    # A key, so a PUT passes validation and actually saves.
    "llm": {"api_key": "sk-test-0123456789abcdef"},
    "pipeline": {
        "image_provider": "flowkit",
        "character_consistency_provider": "flowkit",
        "flowkit_enabled": True,
        "flowkit_project_id": "abc",
        "qwen_local_api_key": "x",
        "codex_model": "gpt-5.5",
    }
}


@pytest.fixture
def old_config_file(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(_OLD_CONFIG), encoding="utf-8")
    monkeypatch.setattr(persistence, "CONFIG_FILE", str(path))
    monkeypatch.delenv("STORYFORGE_IMAGE_PROVIDER", raising=False)
    return path


@pytest.fixture
def fresh_config_manager():
    """A ConfigManager singleton built from the patched CONFIG_FILE, then restored."""
    previous = ConfigManager._instance
    ConfigManager._instance = None
    try:
        yield
    finally:
        ConfigManager._instance = previous


def _api_client() -> TestClient:
    from api import api_router

    app = FastAPI()
    app.include_router(api_router)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client():
    return _api_client()


@pytest.fixture
def client_with_flowkit_config(old_config_file, fresh_config_manager):
    return _api_client()


# ── config upgrade path ──────────────────────────────────────────────────────


def test_old_config_with_flowkit_provider_loads_as_none(old_config_file):
    llm, pipe = LLMConfig(), PipelineConfig()
    load_config(llm, pipe)
    assert pipe.image_provider == "none"
    assert pipe.image_provider_notice == "flowkit"
    assert not hasattr(pipe, "flowkit_enabled")
    assert not hasattr(pipe, "qwen_local_api_key")
    assert not hasattr(pipe, "codex_model")


def test_old_consistency_provider_is_also_reset(old_config_file):
    llm, pipe = LLMConfig(), PipelineConfig()
    load_config(llm, pipe)
    assert pipe.character_consistency_provider == "none"


@pytest.mark.parametrize("removed", ["codex", "flowkit", "qwen-local"])
def test_every_removed_provider_maps_to_none(tmp_path, monkeypatch, removed):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"pipeline": {"image_provider": removed}}), encoding="utf-8"
    )
    monkeypatch.setattr(persistence, "CONFIG_FILE", str(path))
    monkeypatch.delenv("STORYFORGE_IMAGE_PROVIDER", raising=False)
    llm, pipe = LLMConfig(), PipelineConfig()
    load_config(llm, pipe)
    assert pipe.image_provider == "none"
    assert pipe.image_provider_notice == removed


def test_env_override_to_removed_provider_is_also_reset(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "CONFIG_FILE", str(tmp_path / "absent.json"))
    monkeypatch.setenv("STORYFORGE_IMAGE_PROVIDER", "qwen-local")
    llm, pipe = LLMConfig(), PipelineConfig()
    load_config(llm, pipe)
    assert pipe.image_provider == "none"
    assert pipe.image_provider_notice == "qwen-local"


def test_supported_provider_has_no_notice(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"pipeline": {"image_provider": "dalle"}}), encoding="utf-8"
    )
    monkeypatch.setattr(persistence, "CONFIG_FILE", str(path))
    monkeypatch.delenv("STORYFORGE_IMAGE_PROVIDER", raising=False)
    llm, pipe = LLMConfig(), PipelineConfig()
    load_config(llm, pipe)
    assert pipe.image_provider == "dalle"
    assert pipe.image_provider_notice == ""


def test_save_drops_removed_provider_keys_and_never_persists_notice(old_config_file):
    llm, pipe = LLMConfig(), PipelineConfig()
    load_config(llm, pipe)
    save_config(llm, pipe)
    saved = json.loads(old_config_file.read_text(encoding="utf-8"))["pipeline"]
    leftovers = [
        k for k in saved if k.startswith(("flowkit_", "qwen_local_", "codex_"))
    ]
    assert leftovers == []
    assert "image_provider_notice" not in saved
    assert saved["image_provider"] == "none"


# ── API surface ──────────────────────────────────────────────────────────────


def test_get_config_reports_notice_once(client_with_flowkit_config):
    r = client_with_flowkit_config.get("/api/config")
    assert r.status_code == 200, r.text
    notices = r.json()["notices"]
    assert "image_provider_removed:flowkit" in notices
    # image_provider and character_consistency_provider were both "flowkit";
    # the user still gets one notice, not two.
    assert notices.count("image_provider_removed:flowkit") == 1


def test_get_config_has_no_removed_provider_fields(client_with_flowkit_config):
    pipeline = client_with_flowkit_config.get("/api/config").json()["pipeline"]
    leftovers = [
        k for k in pipeline if k.startswith(("flowkit_", "qwen_local_", "codex_"))
    ]
    assert leftovers == []
    assert pipeline["image_provider"] == "none"


def test_get_config_notices_empty_by_default(client):
    assert client.get("/api/config").json()["notices"] == []


def test_put_rejects_a_removed_provider(client):
    r = client.put("/api/config", json={"image_provider": "flowkit"})
    assert r.status_code == 400


def test_put_with_a_supported_provider_clears_the_notice(
    client_with_flowkit_config,
):
    r = client_with_flowkit_config.put("/api/config", json={"image_provider": "dalle"})
    assert r.status_code == 200, r.text
    assert client_with_flowkit_config.get("/api/config").json()["notices"] == []


def test_flowkit_routes_gone(client):
    assert client.get("/api/flowkit/status").status_code == 404
    assert client.post("/api/ext/callback", json={}).status_code in (403, 404)
    assert client.get("/api/config/qwen-local/status").status_code in (404, 405)


def test_ext_callback_no_longer_csrf_exempt():
    from middleware import csrf

    assert not any("ext/callback" in p for p in csrf._EXEMPT_PREFIXES)


def test_gemini_web_preset_gone(client):
    presets = client.get("/api/config/provider-presets").json()["presets"]
    names = [p["name"] for p in presets]
    assert not any("Gemini Web" in n for n in names)
    assert not any("default_key" in p for p in presets)


@pytest.mark.parametrize(
    "module",
    [
        "api.flowkit",
        "services.media.flow_service",
        "services.media.codex_image_client",
        "services.media.qwen_local_client",
    ],
)
def test_removed_modules_are_gone(module):
    assert importlib.util.find_spec(module) is None


# ── image generation ─────────────────────────────────────────────────────────


def test_image_generator_providers():
    from services.media.image_generator import ImageGenerator

    assert ImageGenerator.PROVIDERS == [
        "none",
        "dalle",
        "sd-api",
        "seedream",
        "huggingface",
        "replicate",
    ]


def test_ref_capable_providers():
    from services.media.comic_chapter import REF_CAPABLE

    assert REF_CAPABLE == {"seedream", "replicate"}


def test_compositor_runs_for_every_provider():
    """Codex used to bake balloons into the art and skip the compositor."""
    from types import SimpleNamespace

    from services.media.comic_chapter import ComicSettings

    cfg = SimpleNamespace(comic_shot_list_enabled=True, comic_compositor_enabled=True)
    assert ComicSettings(cfg, provider="codex").compose_pages is True
    assert ComicSettings(cfg, provider="dalle").compose_pages is True


def test_dialogue_baking_is_gone():
    import services.media.image_prompt_generator as ipg

    assert not hasattr(ipg, "bake_dialogue_into_prompts")


# ── avatars and covers go through the configured provider ───────────────────


_CHAR_PAYLOAD = {
    "name": "Lý Trầm",
    "role": "protagonist",
    "traits": {"strength": 70, "wisdom": 60, "agility": 80, "scheme": 40},
    "description": "Mặt lạnh, đeo kiếm gãy.",
    "backstory": "Mất sư phụ.",
    "secret": "Hậu duệ tà phái.",
    "conflict": "Tha thứ hay báo thù.",
}


def _char():
    from models.schemas import ForgeCharacter

    return ForgeCharacter(**_CHAR_PAYLOAD)


def test_character_avatar_uses_configured_provider(monkeypatch, tmp_path):
    from services import character_avatar
    from services.media.image_generator import ImageGenerator

    monkeypatch.setattr(ConfigManager().pipeline, "image_provider", "dalle")
    seen = {}

    def fake_generate(self, prompt, filename="image.png", size="1024x1024"):
        seen["provider"] = self.provider
        seen["output_dir"] = self.output_dir
        path = tmp_path / filename
        path.write_bytes(b"png")
        return str(path)

    monkeypatch.setattr(ImageGenerator, "generate", fake_generate)
    monkeypatch.setattr(
        character_avatar,
        "_avatar_dirs",
        lambda story_id: (str(tmp_path), "story/images/avatars"),
    )

    url = asyncio.run(character_avatar.generate_character_avatar(_char(), "s1"))

    assert url and url.startswith("/media/story/images/avatars/")
    assert seen["provider"] == "dalle"
    assert seen["output_dir"] == str(tmp_path)
    assert "services.media.flow_service" not in sys.modules


def test_character_avatar_with_no_provider_raises():
    from services import character_avatar
    from services.media.image_generator import ImageProviderNotConfigured

    cfg = ConfigManager().pipeline
    with patch.object(cfg, "image_provider", "none"):
        with pytest.raises(ImageProviderNotConfigured):
            asyncio.run(character_avatar.generate_character_avatar(_char(), "s1"))


def test_character_avatar_with_no_provider_raises_clear_error(monkeypatch):
    from api.character_routes import router as character_router

    monkeypatch.setattr(ConfigManager().pipeline, "image_provider", "none")
    monkeypatch.setattr(
        ConfigManager().pipeline, "enable_character_traits", True, raising=False
    )
    app = FastAPI()
    app.include_router(character_router, prefix="/api")
    client = TestClient(app, raise_server_exceptions=False)

    r = client.post(
        "/api/characters/avatar",
        json={
            "character": _CHAR_PAYLOAD,
            "story_id": "s1",
        },
    )

    assert r.status_code == 409, r.text
    assert r.json()["code"] == "image_provider_not_configured"


def test_cover_with_no_provider_is_skipped_quietly(monkeypatch):
    from services.cover_image import generate_story_cover

    monkeypatch.setattr(ConfigManager().pipeline, "image_provider", "none")
    monkeypatch.setattr(ConfigManager().pipeline, "cover_image_enabled", True)
    assert asyncio.run(generate_story_cover("T", story_id="story-1")) is None


def test_cover_uses_configured_provider(monkeypatch, tmp_path):
    import services.output_paths as output_paths
    from services.cover_image import generate_story_cover
    from services.media.image_generator import ImageGenerator

    monkeypatch.setattr(ConfigManager().pipeline, "image_provider", "seedream")
    monkeypatch.setattr(ConfigManager().pipeline, "cover_image_enabled", True)
    monkeypatch.setattr(output_paths, "images_dir", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(output_paths, "media_url", lambda p: "/media/x/cover.png")
    seen = {}

    def fake_generate(self, prompt, filename="image.png", size="1024x1024"):
        seen["provider"] = self.provider
        seen["filename"] = filename
        path = tmp_path / filename
        path.write_bytes(b"png")
        return str(path)

    monkeypatch.setattr(ImageGenerator, "generate", fake_generate)

    url = asyncio.run(generate_story_cover("T", story_id="story-1"))

    assert url and url.startswith("/media/x/cover.png")
    assert seen == {"provider": "seedream", "filename": "cover.png"}


def test_removed_provider_constant():
    assert persistence.REMOVED_IMAGE_PROVIDERS == frozenset(
        {"flowkit", "codex", "qwen-local"}
    )


def test_bulk_avatar_generation_with_no_provider_is_409(monkeypatch):
    from api.character_routes import router as character_router

    monkeypatch.setattr(ConfigManager().pipeline, "image_provider", "none")
    app = FastAPI()
    app.include_router(character_router, prefix="/api")
    client = TestClient(app, raise_server_exceptions=False)

    r = client.post(
        "/api/characters/avatars/generate",
        json={"characters": [_CHAR_PAYLOAD], "story_id": "s1"},
    )

    assert r.status_code == 409, r.text
    assert r.json()["code"] == "image_provider_not_configured"
