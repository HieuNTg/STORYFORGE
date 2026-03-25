"""Tests for ImageGenerator.generate_with_reference() and related helpers."""

from unittest.mock import MagicMock, patch
import pytest

from services.image_generator import ImageGenerator


# ---------------------------------------------------------------------------
# PROVIDERS list
# ---------------------------------------------------------------------------


def test_providers_includes_replicate():
    assert "replicate" in ImageGenerator.PROVIDERS


def test_providers_includes_existing():
    for p in ("dalle", "sd-api", "seedream", "none"):
        assert p in ImageGenerator.PROVIDERS


# ---------------------------------------------------------------------------
# generate_with_reference — routing
# ---------------------------------------------------------------------------


def test_generate_with_reference_no_refs_falls_back_to_generate(tmp_path):
    """Empty reference_paths must delegate to regular generate()."""
    gen = ImageGenerator(provider="dalle")
    gen.output_dir = str(tmp_path)
    with patch.object(gen, "generate", return_value="/some/path.png") as mock_gen:
        result = gen.generate_with_reference("a prompt", [], "out.png")
    mock_gen.assert_called_once_with("a prompt", "out.png", "1024x1024")
    assert result == "/some/path.png"


def test_generate_with_reference_dalle_falls_back_to_text_only(tmp_path):
    """DALL-E provider has no native reference support → text-only fallback."""
    gen = ImageGenerator(provider="dalle")
    gen.output_dir = str(tmp_path)
    with patch.object(gen, "generate", return_value="/dalle/out.png") as mock_gen:
        result = gen.generate_with_reference("prompt", ["/ref.png"], "out.png")
    mock_gen.assert_called_once_with("prompt", "out.png", "1024x1024")
    assert result == "/dalle/out.png"


def test_generate_with_reference_sd_falls_back_to_text_only(tmp_path):
    """SD-api provider has no native reference support → text-only fallback."""
    gen = ImageGenerator(provider="sd-api")
    gen.output_dir = str(tmp_path)
    with patch.object(gen, "generate", return_value="/sd/out.png") as mock_gen:
        result = gen.generate_with_reference("prompt", ["/ref.png"], "out.png")
    mock_gen.assert_called_once_with("prompt", "out.png", "1024x1024")
    assert result == "/sd/out.png"


def test_generate_with_reference_seedream_calls_seedream_with_ref(tmp_path):
    """Seedream provider must delegate to _seedream_with_ref."""
    gen = ImageGenerator(provider="seedream")
    gen.output_dir = str(tmp_path)
    with patch.object(gen, "_seedream_with_ref", return_value="/seedream/out.png") as mock_sr:
        result = gen.generate_with_reference("prompt", ["/ref.png"], "out.png")
    mock_sr.assert_called_once_with("prompt", ["/ref.png"], "out.png")
    assert result == "/seedream/out.png"


def test_generate_with_reference_replicate_calls_replicate_with_ref(tmp_path):
    """Replicate provider must delegate to _replicate_with_ref with first ref only."""
    gen = ImageGenerator(provider="replicate")
    gen.output_dir = str(tmp_path)
    with patch.object(gen, "_replicate_with_ref", return_value="/rep/out.png") as mock_rr:
        result = gen.generate_with_reference("prompt", ["/ref1.png", "/ref2.png"], "out.png")
    mock_rr.assert_called_once_with("prompt", "/ref1.png", "out.png")
    assert result == "/rep/out.png"


# ---------------------------------------------------------------------------
# _seedream_with_ref
# ---------------------------------------------------------------------------


def test_seedream_with_ref_not_configured_falls_back(tmp_path):
    """When Seedream is not configured, fall back to text-only generate()."""
    import sys
    gen = ImageGenerator(provider="seedream")
    gen.output_dir = str(tmp_path)

    mock_client = MagicMock()
    mock_client.is_configured.return_value = False
    mock_seedream_module = MagicMock()
    mock_seedream_module.SeedreamClient = MagicMock(return_value=mock_client)

    sys.modules["services.seedream_client"] = mock_seedream_module
    try:
        with patch.object(gen, "generate", return_value="/fallback.png") as mock_gen:
            result = gen._seedream_with_ref("prompt", ["/r.png"], "out.png")
    finally:
        del sys.modules["services.seedream_client"]

    mock_gen.assert_called_once_with("prompt", "out.png")
    assert result == "/fallback.png"


def test_seedream_with_ref_configured_calls_generate_scene(tmp_path):
    import sys
    gen = ImageGenerator(provider="seedream")
    gen.output_dir = str(tmp_path)

    mock_client = MagicMock()
    mock_client.is_configured.return_value = True
    mock_client.generate_scene.return_value = "/seedream/scene.png"
    mock_seedream_module = MagicMock()
    mock_seedream_module.SeedreamClient = MagicMock(return_value=mock_client)

    import os
    expected_filepath = os.path.join(str(tmp_path), "out.png")

    sys.modules["services.seedream_client"] = mock_seedream_module
    try:
        result = gen._seedream_with_ref("prompt", ["/r.png"], "out.png")
    finally:
        del sys.modules["services.seedream_client"]

    mock_client.generate_scene.assert_called_once_with("prompt", ["/r.png"], expected_filepath)
    assert result == "/seedream/scene.png"


# ---------------------------------------------------------------------------
# _replicate_with_ref
# ---------------------------------------------------------------------------


def test_replicate_with_ref_not_configured_falls_back(tmp_path):
    import sys
    gen = ImageGenerator(provider="replicate")
    gen.output_dir = str(tmp_path)

    mock_client = MagicMock()
    mock_client.is_configured.return_value = False
    mock_module = MagicMock()
    mock_module.ReplicateIPAdapter = MagicMock(return_value=mock_client)
    sys.modules["services.replicate_ip_adapter"] = mock_module
    try:
        with patch.object(gen, "generate", return_value="/fallback.png") as mock_gen:
            result = gen._replicate_with_ref("prompt", "/r.png", "out.png")
    finally:
        del sys.modules["services.replicate_ip_adapter"]

    mock_gen.assert_called_once_with("prompt", "out.png")
    assert result == "/fallback.png"


def test_replicate_with_ref_configured_calls_client_generate(tmp_path):
    import sys
    gen = ImageGenerator(provider="replicate")
    gen.output_dir = str(tmp_path)

    mock_client = MagicMock()
    mock_client.is_configured.return_value = True
    mock_client.generate.return_value = "/replicate/out.png"
    mock_module = MagicMock()
    mock_module.ReplicateIPAdapter = MagicMock(return_value=mock_client)
    sys.modules["services.replicate_ip_adapter"] = mock_module
    try:
        result = gen._replicate_with_ref("prompt", "/r.png", "out.png")
    finally:
        del sys.modules["services.replicate_ip_adapter"]

    mock_client.generate.assert_called_once_with("prompt", "/r.png", "out.png")
    assert result == "/replicate/out.png"
