"""Test ImagePromptGenerator service."""
from models.schemas import StoryboardPanel, ShotType
from services.image_prompt_generator import ImagePromptGenerator


def test_generate_from_panel_basic():
    gen = ImagePromptGenerator(style="cinematic")
    panel = StoryboardPanel(
        panel_number=1, chapter_number=1,
        shot_type=ShotType.WIDE,
        description="A dark forest at night",
        characters_in_frame=["Minh"],
    )
    result = gen.generate_from_panel(panel)
    assert result.dalle_prompt != ""
    assert result.sd_prompt != ""
    assert result.panel_number == 1
    assert result.style == "cinematic"


def test_generate_from_panel_with_chars():
    gen = ImagePromptGenerator(style="anime")
    panel = StoryboardPanel(
        panel_number=2, chapter_number=1,
        shot_type=ShotType.CLOSE_UP,
        description="Character looking at sunset",
        characters_in_frame=["Linh"],
    )
    chars = {"Linh": "young woman with long black hair"}
    result = gen.generate_from_panel(panel, characters=chars)
    assert "Linh" in result.dalle_prompt or "young woman" in result.dalle_prompt
    assert result.negative_prompt != ""


def test_default_style():
    gen = ImagePromptGenerator()
    assert gen.style != ""
