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
