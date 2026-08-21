"""Tests for the Qwen local proxy image provider.

All HTTP is mocked — no proxy process is required to run these. Covers the
client (request shape, save path, failure modes), the ImageGenerator routing
that selects it, and the ImageProvider gate the media stage consults.
"""

import base64
from unittest.mock import MagicMock, patch

import pytest

from services.image_generator import ImageGenerator
from services.media.qwen_local_client import QwenLocalClient

PNG_BYTES = b"\x89PNG\r\n\x1a\nqwen-local-test"
PNG_B64 = base64.b64encode(PNG_BYTES).decode()


def _image_response(b64: str = PNG_B64, status: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status
    response.json.return_value = {
        "created": 1,
        "data": [{"url": None, "b64_json": b64, "revised_prompt": None}],
        "model": "qwen3.8-max-image",
        "size": "1:1",
    }
    return response


# ---------------------------------------------------------------------------
# text_to_image
# ---------------------------------------------------------------------------


def test_text_to_image_posts_and_saves(tmp_path):
    client = QwenLocalClient(base_url="http://localhost:8000/v1", api_key="k")
    out = tmp_path / "panel.png"

    with patch("requests.post", return_value=_image_response()) as post:
        result = client.text_to_image("a red panda", str(out))

    assert result == str(out)
    assert out.read_bytes() == PNG_BYTES
    url, kwargs = post.call_args[0][0], post.call_args[1]
    assert url == "http://localhost:8000/v1/images/qwen"
    assert kwargs["json"]["prompt"] == "a red panda"
    # b64 so the bytes arrive inline instead of via the proxy's static mount.
    assert kwargs["json"]["response_format"] == "b64_json"
    assert kwargs["headers"]["Authorization"] == "Bearer k"


def test_text_to_image_sends_configured_size_and_model(tmp_path):
    client = QwenLocalClient(
        base_url="http://localhost:8000/v1", model="qwen3.8-max-image", size="16:9"
    )
    with patch("requests.post", return_value=_image_response()) as post:
        client.text_to_image("x", str(tmp_path / "a.png"))
    body = post.call_args[1]["json"]
    assert body["size"] == "16:9"
    assert body["model"] == "qwen3.8-max-image"


def test_per_call_size_overrides_configured_size(tmp_path):
    client = QwenLocalClient(base_url="http://localhost:8000/v1", size="1:1")
    with patch("requests.post", return_value=_image_response()) as post:
        client.text_to_image("x", str(tmp_path / "a.png"), size="9:16")
    assert post.call_args[1]["json"]["size"] == "9:16"


def test_no_api_key_sends_no_auth_header(tmp_path):
    client = QwenLocalClient(base_url="http://localhost:8000/v1")
    with patch("requests.post", return_value=_image_response()) as post:
        client.text_to_image("x", str(tmp_path / "a.png"))
    assert "Authorization" not in post.call_args[1]["headers"]


# ---------------------------------------------------------------------------
# failure modes — every one must return None, never raise
# ---------------------------------------------------------------------------


def test_unreachable_proxy_returns_none(tmp_path):
    import requests

    client = QwenLocalClient(base_url="http://localhost:8000/v1")
    with patch("requests.post", side_effect=requests.ConnectionError("refused")):
        assert client.text_to_image("x", str(tmp_path / "a.png")) is None


def test_http_error_returns_none(tmp_path):
    client = QwenLocalClient(base_url="http://localhost:8000/v1")
    error = MagicMock()
    error.status_code = 503
    error.json.return_value = {"detail": "Qwen provider is not available"}
    with patch("requests.post", return_value=error):
        assert client.text_to_image("x", str(tmp_path / "a.png")) is None


def test_empty_data_returns_none(tmp_path):
    client = QwenLocalClient(base_url="http://localhost:8000/v1")
    empty = MagicMock()
    empty.status_code = 200
    empty.json.return_value = {"created": 1, "data": []}
    with patch("requests.post", return_value=empty):
        assert client.text_to_image("x", str(tmp_path / "a.png")) is None


def test_unconfigured_client_returns_none(tmp_path):
    client = QwenLocalClient(base_url="")
    assert client.is_configured() is False
    with patch("requests.post") as post:
        assert client.text_to_image("x", str(tmp_path / "a.png")) is None
    post.assert_not_called()


# ---------------------------------------------------------------------------
# image_with_refs (edit mode)
# ---------------------------------------------------------------------------


def test_image_with_refs_uploads_source_to_edit_endpoint(tmp_path):
    source = tmp_path / "ref.png"
    source.write_bytes(PNG_BYTES)
    client = QwenLocalClient(base_url="http://localhost:8000/v1")

    with patch("requests.post", return_value=_image_response()) as post:
        result = client.image_with_refs(
            "make it night", [str(source)], str(tmp_path / "out.png")
        )

    assert result == str(tmp_path / "out.png")
    assert post.call_args[0][0] == "http://localhost:8000/v1/images/qwen/edits"
    body = post.call_args[1]["json"]
    assert body["image"] == PNG_B64
    assert body["filename"] == "ref.png"


def test_image_with_refs_missing_file_falls_back_to_text_only(tmp_path):
    client = QwenLocalClient(base_url="http://localhost:8000/v1")
    with patch("requests.post", return_value=_image_response()) as post:
        client.image_with_refs(
            "prompt", [str(tmp_path / "nope.png")], str(tmp_path / "out.png")
        )
    assert post.call_args[0][0].endswith("/images/qwen")


def test_image_with_refs_oversized_source_falls_back_to_text_only(tmp_path):
    from services.media import qwen_local_client as module

    source = tmp_path / "big.png"
    source.write_bytes(b"x" * (module.MAX_REFERENCE_BYTES + 1))
    client = QwenLocalClient(base_url="http://localhost:8000/v1")
    with patch("requests.post", return_value=_image_response()) as post:
        client.image_with_refs("prompt", [str(source)], str(tmp_path / "out.png"))
    assert post.call_args[0][0].endswith("/images/qwen")


# ---------------------------------------------------------------------------
# status probe
# ---------------------------------------------------------------------------


def test_health_url_drops_the_v1_suffix():
    client = QwenLocalClient(base_url="http://localhost:8000/v1")
    assert client.health_url == "http://localhost:8000/health"


@pytest.mark.parametrize(
    "providers, expect_ready",
    [({"qwen": True, "gemini": True}, True), ({"qwen": False, "gemini": True}, False)],
)
def test_status_reports_whether_qwen_started(providers, expect_ready):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"status": "ok", "providers": providers}
    client = QwenLocalClient(base_url="http://localhost:8000/v1")
    with patch("requests.get", return_value=response):
        status = client.status()
    assert status["reachable"] is True
    assert status["qwen_ready"] is expect_ready
    # A reachable proxy whose Qwen never started must still explain itself.
    assert bool(status["error"]) is not expect_ready


def test_status_survives_a_dead_proxy():
    import requests

    client = QwenLocalClient(base_url="http://localhost:8000/v1")
    with patch("requests.get", side_effect=requests.ConnectionError("refused")):
        status = client.status()
    assert status == {
        "configured": True,
        "reachable": False,
        "qwen_ready": False,
        "base_url": "http://localhost:8000/v1",
        "error": "refused",
    }


# ---------------------------------------------------------------------------
# ImageGenerator routing
# ---------------------------------------------------------------------------


def test_providers_list_includes_qwen_local():
    assert "qwen-local" in ImageGenerator.PROVIDERS


def test_generate_routes_to_qwen_local(tmp_path):
    gen = ImageGenerator(provider="qwen-local")
    gen.output_dir = str(tmp_path)
    with patch.object(gen, "_generate_qwen_local", return_value="p.png") as route:
        assert gen.generate("prompt", "p.png", "1024x1024") == "p.png"
    route.assert_called_once_with("prompt", "p.png", "1024x1024")


def test_generate_with_reference_routes_to_edit(tmp_path):
    gen = ImageGenerator(provider="qwen-local")
    gen.output_dir = str(tmp_path)
    with patch.object(gen, "_qwen_local_with_ref", return_value="p.png") as route:
        gen.generate_with_reference("prompt", ["/a/ref.png"], "p.png")
    route.assert_called_once_with("prompt", ["/a/ref.png"], "p.png", "1024x1024")


def test_edit_for_refs_toggle_off_uses_text_only(tmp_path):
    """qwen_local_use_edit_for_refs=False must skip the edit endpoint."""
    gen = ImageGenerator(provider="qwen-local")
    gen.output_dir = str(tmp_path)
    client = MagicMock()
    client.is_configured.return_value = True
    cfg = MagicMock()
    cfg.pipeline.qwen_local_use_edit_for_refs = False

    with (
        patch.object(gen, "_qwen_local_client", return_value=client),
        patch("services.media.image_generator.ConfigManager", return_value=cfg),
    ):
        gen._qwen_local_with_ref("prompt", ["/a/ref.png"], "p.png", "1024x1024")

    client.text_to_image.assert_called_once()
    client.image_with_refs.assert_not_called()


# ---------------------------------------------------------------------------
# ImageProvider gate (media stage consults this before making avatars)
# ---------------------------------------------------------------------------


def test_image_provider_is_configured_for_qwen_local():
    from services.media.image_provider import ImageProvider

    cfg = MagicMock()
    cfg.pipeline.image_provider = "qwen-local"
    provider = ImageProvider()
    client = MagicMock()
    client.is_configured.return_value = True
    provider._qwen_local = client

    with patch("config.ConfigManager", return_value=cfg):
        assert provider.is_configured() is True


def test_character_reference_routes_to_qwen_local(tmp_path):
    from services.media.image_provider import ImageProvider

    cfg = MagicMock()
    cfg.pipeline.image_provider = "qwen-local"
    provider = ImageProvider()
    client = MagicMock()
    client.text_to_image.return_value = "ref.png"
    provider._qwen_local = client

    with patch("config.ConfigManager", return_value=cfg):
        assert provider.generate_character_reference("Lan", "cô gái tóc dài") == "ref.png"

    prompt = client.text_to_image.call_args[0][0]
    assert "cô gái tóc dài" in prompt
    assert client.text_to_image.call_args[0][1].endswith("lan_reference.png")
