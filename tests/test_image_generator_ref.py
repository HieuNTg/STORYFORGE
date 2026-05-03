"""Tests for ImageGenerator.generate_with_reference() and related helpers."""

from unittest.mock import MagicMock, patch

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


# ---------------------------------------------------------------------------
# generate_story_images — character_references routing
# ---------------------------------------------------------------------------


def _make_prompt(scene_chars):
    p = MagicMock()
    p.dalle_prompt = "dalle"
    p.sd_prompt = "sd"
    p.scene_description = "scene"
    p.characters_in_scene = scene_chars
    return p


def test_generate_story_images_routes_through_reference_when_ref_available(tmp_path):
    """Scene mentions a character with a reference → generate_with_reference is used."""
    gen = ImageGenerator(provider="seedream")
    gen.output_dir = str(tmp_path)
    ref_path = tmp_path / "hero.png"
    ref_path.write_bytes(b"\x89PNG")

    prompt = _make_prompt(["Hero"])
    with patch.object(gen, "generate_with_reference", return_value="/scene.png") as gwr, \
         patch.object(gen, "generate") as g:
        paths = gen.generate_story_images(
            [prompt],
            chapter_number=1,
            character_references={"Hero": str(ref_path)},
        )
    gwr.assert_called_once()
    g.assert_not_called()
    assert paths == ["/scene.png"]


def test_generate_story_images_no_refs_uses_text_only(tmp_path):
    """No character_references → original text-only path (backward compat)."""
    gen = ImageGenerator(provider="dalle")
    gen.output_dir = str(tmp_path)

    prompt = _make_prompt(["Hero"])
    with patch.object(gen, "generate_with_reference") as gwr, \
         patch.object(gen, "generate", return_value="/text.png") as g:
        paths = gen.generate_story_images([prompt], chapter_number=1)
    gwr.assert_not_called()
    g.assert_called_once()
    assert paths == ["/text.png"]


def test_generate_story_images_skips_missing_files(tmp_path):
    """Reference path that does not exist on disk is filtered out."""
    gen = ImageGenerator(provider="seedream")
    gen.output_dir = str(tmp_path)

    prompt = _make_prompt(["Hero"])
    with patch.object(gen, "generate_with_reference") as gwr, \
         patch.object(gen, "generate", return_value="/text.png") as g:
        paths = gen.generate_story_images(
            [prompt],
            chapter_number=1,
            character_references={"Hero": str(tmp_path / "missing.png")},
        )
    gwr.assert_not_called()
    g.assert_called_once()
    assert paths == ["/text.png"]


def test_generate_with_reference_unsupported_provider_logs_and_drops(tmp_path, caplog):
    """Unsupported provider logs a single info line and drops refs."""
    import logging
    gen = ImageGenerator(provider="dalle")
    gen.output_dir = str(tmp_path)
    with caplog.at_level(logging.INFO, logger="services.media.image_generator"), \
         patch.object(gen, "generate", return_value="/out.png"):
        gen.generate_with_reference("prompt", ["/r.png"], "out.png")
    assert any("does not support reference" in rec.message for rec in caplog.records)
