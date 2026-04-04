"""Tests for visual_profiles injection in ImagePromptGenerator."""

from unittest.mock import patch

from models.schemas import Chapter, Character
from services.image_prompt_generator import ImagePromptGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_generator():
    gen = ImagePromptGenerator(style="anime")
    return gen


def _make_chapter():
    return Chapter(chapter_number=1, title="Ch1", content="A story about Minh and Lan.")


def _make_characters():
    c1 = Character(
        name="Minh", role="main", personality="brave", background="orphan",
        motivation="revenge", appearance="tall man"
    )
    c2 = Character(
        name="Lan", role="support", personality="gentle", background="noble",
        motivation="love", appearance="short woman"
    )
    return [c1, c2]


# ---------------------------------------------------------------------------
# generate_from_chapter
# ---------------------------------------------------------------------------


def test_generate_from_chapter_without_visual_profiles_backward_compat():
    """No visual_profiles → original behavior (appearance used as desc)."""
    gen = _make_generator()
    chapter = _make_chapter()
    chars = _make_characters()

    mock_result = {"scenes": [
        {"scene_description": "s1", "dalle_prompt": "d1", "sd_prompt": "sd1",
         "negative_prompt": "n1", "characters_in_scene": ["Minh"]},
    ]}
    with patch.object(gen.llm, "generate_json", return_value=mock_result) as mock_llm:
        prompts = gen.generate_from_chapter(chapter, characters=chars, num_images=1)
        call_kwargs = mock_llm.call_args
        user_prompt = call_kwargs[1]["user_prompt"] if call_kwargs[1] else call_kwargs[0][1]

    assert "tall man" in user_prompt
    assert len(prompts) == 1


def test_generate_from_chapter_with_visual_profiles_injects_frozen_desc():
    """visual_profiles replaces character appearance in LLM prompt."""
    gen = _make_generator()
    chapter = _make_chapter()
    chars = _make_characters()
    vp = {"Minh": "frozen-minh-visual", "Lan": "frozen-lan-visual"}

    mock_result = {"scenes": [
        {"scene_description": "s1", "dalle_prompt": "d1", "sd_prompt": "sd1",
         "negative_prompt": "n1", "characters_in_scene": ["Minh"]},
    ]}
    with patch.object(gen.llm, "generate_json", return_value=mock_result) as mock_llm:
        gen.generate_from_chapter(chapter, characters=chars, num_images=1, visual_profiles=vp)
        call_kwargs = mock_llm.call_args
        user_prompt = call_kwargs[1]["user_prompt"] if call_kwargs[1] else call_kwargs[0][1]

    assert "frozen-minh-visual" in user_prompt
    assert "frozen-lan-visual" in user_prompt
    assert "tall man" not in user_prompt
