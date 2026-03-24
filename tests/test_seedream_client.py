"""Tests for SeedreamClient service."""
import base64
import os
from unittest.mock import MagicMock, patch, mock_open

import pytest

from services.seedream_client import SeedreamClient


# ── Init / is_configured ──────────────────────────────────────────────────────

def test_init_no_key_not_configured():
    client = SeedreamClient(api_key="", base_url="https://api.aimlapi.com/v2")
    assert not client.is_configured()


def test_init_with_key_configured():
    client = SeedreamClient(api_key="sk-test-123")
    assert client.is_configured()


def test_init_env_key(monkeypatch):
    monkeypatch.setenv("SEEDREAM_API_KEY", "env-key")
    client = SeedreamClient()
    assert client.is_configured()
    assert client.api_key == "env-key"


# ── generate_character_reference ─────────────────────────────────────────────

def test_generate_character_reference_no_key():
    client = SeedreamClient(api_key="")
    result = client.generate_character_reference("Hero", "tall warrior")
    assert result is None


def test_generate_character_reference_calls_text_to_image(tmp_path):
    fake_img = b"\x89PNG fake"
    fake_b64 = base64.b64encode(fake_img).decode()

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": [{"b64_json": fake_b64}]}
    mock_resp.raise_for_status.return_value = None

    client = SeedreamClient(api_key="sk-test")
    client.output_dir = str(tmp_path)

    with patch("services.seedream_client.requests.post", return_value=mock_resp):
        result = client.generate_character_reference(
            "Kai", "young warrior with blue eyes", filename="kai.png"
        )

    assert result is not None
    assert os.path.exists(result)
    with open(result, "rb") as f:
        assert f.read() == fake_img


# ── generate_scene ────────────────────────────────────────────────────────────

def test_generate_scene_no_references_uses_text_to_image(tmp_path):
    fake_img = b"scene bytes"
    fake_b64 = base64.b64encode(fake_img).decode()

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": [{"b64_json": fake_b64}]}
    mock_resp.raise_for_status.return_value = None

    client = SeedreamClient(api_key="sk-test")
    client.output_dir = str(tmp_path)

    with patch("services.seedream_client.requests.post", return_value=mock_resp) as mock_post:
        result = client.generate_scene("epic battle scene", [], filename="battle.png")

    assert result is not None
    mock_post.assert_called_once()
    assert "images/generations" in mock_post.call_args[0][0]


def test_generate_scene_with_references_calls_edit_sequential(tmp_path):
    # Create a fake reference image file
    ref_img_path = tmp_path / "ref.png"
    ref_img_path.write_bytes(b"\x89PNG ref image")

    fake_img = b"scene with refs"
    fake_b64 = base64.b64encode(fake_img).decode()

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": [{"b64_json": fake_b64}]}
    mock_resp.raise_for_status.return_value = None

    client = SeedreamClient(api_key="sk-test")
    client.output_dir = str(tmp_path)

    with patch("services.seedream_client.requests.post", return_value=mock_resp) as mock_post:
        result = client.generate_scene(
            "hero in forest", [str(ref_img_path)], filename="scene.png"
        )

    assert result is not None
    assert "images/edits" in mock_post.call_args[0][0]


# ── _save_response_image ──────────────────────────────────────────────────────

def test_save_response_image_b64_json(tmp_path):
    fake_img = b"img data"
    client = SeedreamClient(api_key="k")
    output = str(tmp_path / "out.png")
    response = {"data": [{"b64_json": base64.b64encode(fake_img).decode()}]}
    result = client._save_response_image(response, output)
    assert result == output
    assert open(output, "rb").read() == fake_img


def test_save_response_image_url_format(tmp_path):
    fake_img = b"url fetched image"
    mock_get = MagicMock()
    mock_get.content = fake_img

    client = SeedreamClient(api_key="k")
    output = str(tmp_path / "url_img.png")
    response = {"data": [{"url": "https://cdn.example.com/img.png"}]}

    with patch("services.seedream_client.requests.get", return_value=mock_get):
        result = client._save_response_image(response, output)

    assert result == output
    assert open(output, "rb").read() == fake_img


def test_save_response_image_empty_data_returns_none():
    client = SeedreamClient(api_key="k")
    result = client._save_response_image({"data": []}, "/tmp/x.png")
    assert result is None


def test_save_response_image_unknown_format_returns_none():
    client = SeedreamClient(api_key="k")
    result = client._save_response_image({"data": [{"some_field": "value"}]}, "/tmp/x.png")
    assert result is None
