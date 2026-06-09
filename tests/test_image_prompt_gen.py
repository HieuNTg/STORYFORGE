"""Test ImagePromptGenerator service."""
from models.schemas import Chapter
from services.image_prompt_generator import ImagePromptGenerator


def test_generate_scene_prompt_basic():
    gen = ImagePromptGenerator(style="cinematic")
    chapter = Chapter(chapter_number=1, title="The Beginning", content="Story content", summary="A hero emerges")
    result = gen.generate_scene_prompt(chapter)
    assert result != ""
    assert "cinematic" in result


def test_generate_scene_prompt_uses_summary():
    gen = ImagePromptGenerator(style="anime")
    chapter = Chapter(chapter_number=1, title="Ch1", content="content", summary="battle scene")
    result = gen.generate_scene_prompt(chapter)
    assert "battle scene" in result


def test_generate_scene_prompt_fallback_to_title():
    gen = ImagePromptGenerator(style="anime")
    chapter = Chapter(chapter_number=2, title="The Storm", content="content", summary="")
    result = gen.generate_scene_prompt(chapter)
    assert "The Storm" in result


def test_default_style():
    gen = ImagePromptGenerator()
    assert gen.style != ""


# ---------------------------------------------------------------------------
# Phase 1: comic-panel prompt building (scene extractor + refiner)
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock

from services.media.image_prompt_generator import _SCENE_EXTRACT_PROMPT


def test_default_style_is_comic_not_cinematic():
    """Phase 1: global default style must be a comic style, not 'cinematic'."""
    gen = ImagePromptGenerator()
    low = gen.style.lower()
    assert "comic" in low
    assert low != "cinematic"


def test_scene_extract_template_asks_for_comic_panel():
    """The extraction template must request ONE COMIC PANEL with a varied shot type
    and explicitly forbid in-image text."""
    low = _SCENE_EXTRACT_PROMPT.lower()
    assert "comic panel" in low
    assert "no text" in low  # "Render NO text inside the image" / "NO TEXT in image"
    assert "shot type" in low or "shot_type" in low


def test_refiner_emits_comic_panel_no_text(monkeypatch):
    """The refiner's system prompt must steer toward a comic panel with no text,
    not a cinematic hero shot. We capture the system prompt passed to the LLM."""
    gen = ImagePromptGenerator()
    captured = {}

    def fake_generate(system_prompt, user_prompt, **kw):
        captured["system"] = system_prompt
        return "medium shot, hero reacting, cel shading, no text in image"

    monkeypatch.setattr(gen.llm, "generate", fake_generate, raising=False)
    out = gen.refine_to_cinematic_prompt("hero stands on cliff")

    sys_low = captured["system"].lower()
    assert "comic" in sys_low
    assert "cinematic" not in sys_low
    assert "no text" in sys_low
    # And the refined output itself is a comic-panel prompt, not a cinematic one.
    assert "cel shading" in out.lower()
