"""Tests for ImageGenerator service."""

from unittest.mock import MagicMock, patch
import base64
import os

import pytest


from services.image_generator import ImageGenerator
from models.schemas import ImagePrompt


# ── Init / provider=none ──────────────────────────────────────────────────────


def test_init_default_provider_none():
    gen = ImageGenerator(provider="none")
    assert gen.provider == "none"


def test_generate_returns_none_when_provider_none():
    gen = ImageGenerator(provider="none")
    result = gen.generate("a dramatic forest scene")
    assert result is None


def test_generate_story_images_returns_empty_when_provider_none():
    gen = ImageGenerator(provider="none")
    prompts = [
        ImagePrompt(
            panel_number=1,
            chapter_number=1,
            dalle_prompt="prompt A",
            sd_prompt="sd A",
            scene_description="scene A",
        ),
    ]
    paths = gen.generate_story_images(prompts, chapter_number=1)
    assert paths == []


# ── DALL-E provider (mocked) ──────────────────────────────────────────────────


def test_generate_dalle_saves_file(tmp_path):
    """_generate_dalle decodes b64 and writes file when request succeeds."""
    fake_image = b"\x89PNG fake image bytes"
    fake_b64 = base64.b64encode(fake_image).decode()

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": [{"b64_json": fake_b64}]}
    mock_resp.raise_for_status.return_value = None

    gen = ImageGenerator(provider="dalle", api_key="test-key")
    gen.output_dir = str(tmp_path)

    with patch(
        "services.image_generator.requests.post", return_value=mock_resp
    ) as mock_post:
        result = gen.generate("a hero standing on a cliff", filename="test.png")

    assert result is not None
    assert result.endswith("test.png")
    assert os.path.exists(result)
    with open(result, "rb") as f:
        assert f.read() == fake_image

    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert "images/generations" in call_kwargs[0][0]


def test_generate_dalle_returns_none_on_error():
    gen = ImageGenerator(provider="dalle", api_key="test-key")
    with patch(
        "services.image_generator.requests.post", side_effect=Exception("timeout")
    ):
        result = gen.generate("some prompt", filename="fail.png")
    assert result is None


def test_generate_dalle_returns_none_without_api_key():
    # Hermetic: with no image key AND no OpenAI-compatible LLM key to fall back
    # on, the DALL-E path must short-circuit before any HTTP call. We isolate
    # ConfigManager and the environment so the developer's real configured key
    # can't leak into the resolution chain (image_api_key → IMAGE_API_KEY env →
    # llm.api_key when the LLM is OpenAI). See ImageGenerator.__init__.
    cfg = MagicMock()
    cfg.pipeline.image_provider = "dalle"
    cfg.pipeline.image_api_key = ""
    cfg.pipeline.image_api_url = ""
    cfg.pipeline.hf_token = ""
    cfg.pipeline.hf_image_model = ""
    cfg.llm.api_key = ""
    cfg.llm.base_url = ""  # not openai.com => no llm-key fallback

    with (
        patch("services.image_generator.ConfigManager", return_value=cfg),
        patch.dict(
            os.environ, {"IMAGE_API_KEY": "", "IMAGE_API_URL": "", "HF_TOKEN": ""}
        ),
    ):
        gen = ImageGenerator(provider="dalle", api_key="")

    assert gen.api_key == ""
    # No HTTP call should be made
    with patch("services.image_generator.requests.post") as mock_post:
        result = gen.generate("prompt")
    assert result is None
    mock_post.assert_not_called()


# ── SD-API provider (mocked) ──────────────────────────────────────────────────


def test_generate_sd_saves_file(tmp_path):
    fake_image = b"fake sd image"
    fake_b64 = base64.b64encode(fake_image).decode()

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"images": [fake_b64]}
    mock_resp.raise_for_status.return_value = None

    gen = ImageGenerator(provider="sd-api", base_url="http://localhost:7860")
    gen.output_dir = str(tmp_path)

    with patch("services.image_generator.requests.post", return_value=mock_resp):
        result = gen.generate("fantasy landscape", filename="sd_test.png")

    assert result is not None
    assert os.path.exists(result)


def test_generate_sd_returns_none_on_error():
    gen = ImageGenerator(provider="sd-api", base_url="http://localhost:7860")
    with patch(
        "services.image_generator.requests.post", side_effect=Exception("conn refused")
    ):
        result = gen.generate("prompt", filename="fail.png")
    assert result is None


# ── generate_story_images ─────────────────────────────────────────────────────


def test_generate_story_images_with_mock(tmp_path):
    fake_image = b"fake bytes"
    fake_b64 = base64.b64encode(fake_image).decode()

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": [{"b64_json": fake_b64}]}
    mock_resp.raise_for_status.return_value = None

    gen = ImageGenerator(provider="dalle", api_key="key")
    gen.output_dir = str(tmp_path)

    prompts = [
        ImagePrompt(
            panel_number=1,
            chapter_number=2,
            dalle_prompt="prompt 1",
            sd_prompt="sd 1",
            scene_description="scene 1",
        ),
        ImagePrompt(
            panel_number=2,
            chapter_number=2,
            dalle_prompt="prompt 2",
            sd_prompt="sd 2",
            scene_description="scene 2",
        ),
    ]

    with patch("services.image_generator.requests.post", return_value=mock_resp):
        paths = gen.generate_story_images(prompts, chapter_number=2)

    assert len(paths) == 2
    assert "ch02_panel01.png" in paths[0]
    assert "ch02_panel02.png" in paths[1]


def test_unknown_provider_returns_none():
    gen = ImageGenerator(provider="unknown-provider")
    result = gen.generate("test prompt")
    assert result is None


# ── HuggingFace provider (mocked) ────────────────────────────────────────────


def _make_hf_config(hf_token="hf_test_token", hf_image_model="test/model"):
    """Return a mock ConfigManager whose .pipeline has HuggingFace fields set."""
    mock_cfg = MagicMock()
    mock_cfg.pipeline.image_provider = "huggingface"
    mock_cfg.pipeline.image_api_key = ""
    mock_cfg.pipeline.image_api_url = ""
    mock_cfg.pipeline.hf_token = hf_token
    mock_cfg.pipeline.hf_image_model = hf_image_model
    return mock_cfg


def test_generate_huggingface_saves_file(tmp_path):
    """_generate_huggingface writes raw response content to file on 200 OK."""
    fake_image_data = b"fake_image_data"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = fake_image_data
    mock_resp.raise_for_status.return_value = None

    with patch(
        "services.image_generator.ConfigManager", return_value=_make_hf_config()
    ):
        gen = ImageGenerator(provider="huggingface")
    gen.output_dir = str(tmp_path)

    with patch("services.image_generator.requests.post", return_value=mock_resp):
        result = gen.generate("test prompt", filename="test.png")

    assert result is not None
    assert result.endswith("test.png")
    assert os.path.exists(result)
    with open(result, "rb") as f:
        assert f.read() == fake_image_data


def test_generate_huggingface_retries_on_503(tmp_path):
    """_generate_huggingface retries once when the model returns 503 (loading)."""
    fake_image_data = b"fake_image_data"

    mock_503 = MagicMock()
    mock_503.status_code = 503
    mock_503.content = b""

    mock_200 = MagicMock()
    mock_200.status_code = 200
    mock_200.content = fake_image_data
    mock_200.raise_for_status.return_value = None

    with patch(
        "services.image_generator.ConfigManager", return_value=_make_hf_config()
    ):
        gen = ImageGenerator(provider="huggingface")
    gen.output_dir = str(tmp_path)

    with (
        patch(
            "services.image_generator.requests.post", side_effect=[mock_503, mock_200]
        ) as mock_post,
        patch("services.image_generator.time.sleep", return_value=None),
    ):
        result = gen.generate("test prompt", filename="test.png")

    assert mock_post.call_count == 2
    assert result is not None
    assert os.path.exists(result)
    with open(result, "rb") as f:
        assert f.read() == fake_image_data


def test_generate_huggingface_returns_none_without_token():
    """_generate_huggingface returns None immediately when hf_token is empty."""
    with patch(
        "services.image_generator.ConfigManager",
        return_value=_make_hf_config(hf_token=""),
    ):
        gen = ImageGenerator(provider="huggingface")
    gen.hf_token = ""

    with patch("services.image_generator.requests.post") as mock_post:
        result = gen.generate("test prompt", filename="test.png")

    assert result is None
    mock_post.assert_not_called()


def test_generate_huggingface_returns_none_on_exception():
    """_generate_huggingface swallows exceptions and returns None."""
    with patch(
        "services.image_generator.ConfigManager", return_value=_make_hf_config()
    ):
        gen = ImageGenerator(provider="huggingface")

    with patch(
        "services.image_generator.requests.post",
        side_effect=ConnectionError("test error"),
    ):
        result = gen.generate("test prompt", filename="test.png")

    assert result is None


# ── Output layout ─────────────────────────────────────────────────────────────

@pytest.fixture
def isolated_image_gen_env(tmp_path, monkeypatch):
    """Run image-gen tests in a tmp cwd so output/ writes don't pollute the repo."""
    monkeypatch.chdir(tmp_path)
    yield tmp_path


def test_output_dir_per_session(isolated_image_gen_env):
    from services.media.image_generator import ImageGenerator

    gen = ImageGenerator(
        provider="none", session_id="abc123", story_title="Tiên Hiệp Test!"
    )
    # Per-story layout: images live under output/<story-slug>/images, where the
    # slug is slug_session_dir(title, session_id).
    assert gen.output_dir.replace("\\", "/").endswith(
        "output/tien_hiep_test__abc123/images"
    )
    assert os.path.isdir(gen.output_dir)


def test_output_dir_fallback(isolated_image_gen_env):
    from services.media.image_generator import ImageGenerator

    gen = ImageGenerator(provider="none")
    assert gen.output_dir.replace("\\", "/") == "output/images"


def test_slug_session_dir_helper():
    from services.media._util import slug_session_dir

    assert slug_session_dir("Hello World!", "sid1") == "hello_world__sid1"
    assert slug_session_dir("", "x") == "story_x"
    assert slug_session_dir("a" * 100, "s") == "a" * 60 + "_s"


def test_handlers_relpath_subdirs(isolated_image_gen_env, monkeypatch):
    """services.handlers maps panel paths to OUTPUT_ROOT-relative /media names.

    Under the per-story layout panels live at ``output/<story-slug>/images/...``;
    handlers store the path relative to OUTPUT_ROOT so the ``/media`` mount
    (which serves OUTPUT_ROOT) resolves it as ``/media/<rel>``.
    """
    import services.handlers as handlers_mod

    # Build minimal fake objects to drive handle_generate_images.
    class _Ch:
        chapter_number = 1
        title = "ch1"
        content = "x"
        summary = ""
        images: list = []

    class _Story:
        chapters = [_Ch()]

    class _Output:
        enhanced_story = _Story()
        story_draft = type("D", (), {"title": "T", "characters": []})()

    class _Orch:
        session_id = "sid1"
        output = _Output()

    # Patch the heavy dependencies.
    monkeypatch.setattr(
        "services.media.image_prompt_generator.ImagePromptGenerator.generate_from_chapter",
        lambda self, *a, **kw: [MagicMock(panel_number=1)],
    )
    # Force the legacy scene-extraction path regardless of the local
    # comic_shot_list_enabled flag — the shot-list path calls the real LLM.
    from config import ConfigManager

    monkeypatch.setattr(
        ConfigManager().pipeline,
        "comic_shot_list_enabled",
        False,
        raising=False,
    )

    sub = "output/t_sid1/images"
    os.makedirs(sub, exist_ok=True)
    fake_path = os.path.join(sub, "ch01_panel01.png")

    monkeypatch.setattr(
        "services.media.image_generator.ImageGenerator.generate_story_images",
        lambda self, *a, **kw: [fake_path],
    )

    paths, msg = handlers_mod.handle_generate_images(_Orch(), provider="none")
    assert paths == [fake_path]
    # Chapter image entries keep the full OUTPUT_ROOT-relative path (story slug
    # + images subdir), not just the basename, so /media resolves it.
    assert _Orch.output.enhanced_story.chapters[0].images == [
        "t_sid1/images/ch01_panel01.png"
    ]
