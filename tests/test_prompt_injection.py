"""Tests for visual_profiles injection in ImagePromptGenerator."""

from unittest.mock import MagicMock, patch
import pytest

from models.schemas import StoryboardPanel, Chapter, Character
from services.image_prompt_generator import ImagePromptGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_panel(chars=None):
    from models.schemas import ShotType
    panel = StoryboardPanel(
        panel_number=1,
        chapter_number=1,
        shot_type=ShotType.WIDE,
        description="A hero stands at dawn",
        characters_in_frame=chars or [],
    )
    return panel


def _make_generator():
    gen = ImagePromptGenerator(style="anime")
    return gen


# ---------------------------------------------------------------------------
# generate_from_panel
# ---------------------------------------------------------------------------


def test_generate_from_panel_without_visual_profiles_uses_characters_dict():
    """Backward-compat: characters dict used when no visual_profiles given."""
    gen = _make_generator()
    panel = _make_panel(["Minh"])
    result = gen.generate_from_panel(panel, characters={"Minh": "tall man"})
    assert "Minh" in result.dalle_prompt
    assert "tall man" in result.dalle_prompt


def test_generate_from_panel_with_visual_profiles_uses_frozen_desc():
    """visual_profiles override characters dict."""
    gen = _make_generator()
    panel = _make_panel(["Minh"])
    result = gen.generate_from_panel(
        panel,
        characters={"Minh": "basic desc"},
        visual_profiles={"Minh": "frozen: tall Vietnamese man, black hair"},
    )
    assert "frozen: tall Vietnamese man, black hair" in result.dalle_prompt
    # Basic desc should NOT appear (visual_profile takes precedence)
    assert "basic desc" not in result.dalle_prompt


def test_generate_from_panel_prefers_visual_profiles_over_characters():
    """When both are provided, visual_profiles wins."""
    gen = _make_generator()
    panel = _make_panel(["Lan"])
    result = gen.generate_from_panel(
        panel,
        characters={"Lan": "short woman"},
        visual_profiles={"Lan": "frozen: petite woman, long black hair, bright eyes"},
    )
    assert "frozen" in result.dalle_prompt
    assert "short woman" not in result.dalle_prompt


def test_generate_from_panel_visual_profiles_only_injected_for_chars_in_frame():
    """visual_profiles for chars NOT in frame should NOT appear in prompt."""
    gen = _make_generator()
    panel = _make_panel(["Minh"])
    result = gen.generate_from_panel(
        panel,
        visual_profiles={"Minh": "frozen-minh", "Lan": "frozen-lan"},
    )
    assert "frozen-minh" in result.dalle_prompt
    assert "frozen-lan" not in result.dalle_prompt


def test_generate_from_panel_no_characters_returns_plain_prompt():
    gen = _make_generator()
    panel = _make_panel([])
    result = gen.generate_from_panel(panel)
    assert "A hero stands at dawn" in result.dalle_prompt
    # No character bracket injected
    assert "[" not in result.dalle_prompt


def test_generate_from_panel_returns_image_prompt_with_correct_fields():
    gen = _make_generator()
    panel = _make_panel(["Minh"])
    result = gen.generate_from_panel(panel, visual_profiles={"Minh": "desc"})
    assert result.panel_number == 1
    assert result.chapter_number == 1
    assert result.scene_description == "A hero stands at dawn"
    assert "Minh" in result.characters_in_scene


# ---------------------------------------------------------------------------
# generate_from_chapter
# ---------------------------------------------------------------------------


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
        # Extract what was passed to LLM
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
    # Original appearance should be replaced
    assert "tall man" not in user_prompt
