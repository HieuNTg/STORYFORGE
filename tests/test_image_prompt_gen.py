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


def test_default_style_is_comic_family_not_cinematic():
    """The CODE default art-style must be a comic-family look, never 'cinematic'.

    This checks the art-STYLE direction only. The "it becomes a comic" guarantee
    is STRUCTURAL — enforced by the comic-panel template, the shot-list stage and
    the page compositor regardless of the style string — and is covered by
    ``test_scene_extract_template_asks_for_comic_panel``. So the style string is
    free to be any comic-family look (manga / manhwa / webtoon / anime / ink),
    and a short value like "manga" is perfectly valid. We read the code default
    from ``config/defaults.py`` rather than the gitignored runtime config so the
    test doesn't depend on a user's local settings.
    """
    from config.defaults import PipelineConfig
    default_style = PipelineConfig().image_prompt_style.lower()
    assert default_style != "cinematic"
    assert any(
        k in default_style
        for k in ("manga", "manhwa", "comic", "webtoon", "anime", "ink")
    )


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


# ---------------------------------------------------------------------------
# Codex provider: bake speech bubbles + dialogue INTO the panel prompt
# ---------------------------------------------------------------------------

from models.schemas import ImagePrompt
from services.media.image_prompt_generator import (
    bake_dialogue_into_prompts,
    _strip_no_text_clauses,
)


def test_strip_no_text_clauses_removes_negatives():
    out = _strip_no_text_clauses(
        "medium shot, hero on cliff, cel shading, no text in image, "
        "no speech bubbles, no watermark"
    )
    low = out.lower()
    assert "no text" not in low
    assert "speech bubble" not in low
    assert "watermark" not in low
    # The real content survives.
    assert "hero on cliff" in low
    assert "cel shading" in low


def test_bake_dialogue_injects_verbatim_vietnamese_and_drops_no_text():
    ip = ImagePrompt(
        panel_number=1,
        sd_prompt="close-up, woman shouting, cel shading, no text in image, no captions",
        dalle_prompt="close-up, woman shouting, no speech bubbles",
        dialogue=[{"speaker": "Lan", "type": "shout", "text": "Đừng đi! Tôi cần cậu."}],
    )
    bake_dialogue_into_prompts([ip])
    low = ip.sd_prompt.lower()
    # The clean-panel "no text" instruction is gone...
    assert "no text" not in low
    assert "no speech bubble" not in low
    # ...replaced by an instruction to DRAW bubbles with the exact VN line.
    assert "speech bubbles" in low or "balloon" in low
    assert "Đừng đi! Tôi cần cậu." in ip.sd_prompt  # verbatim, diacritics intact
    assert "Lan" in ip.sd_prompt
    # shout → spiky/burst balloon
    assert "burst" in low or "jagged" in low
    # dalle_prompt is rewritten the same way.
    assert "Đừng đi! Tôi cần cậu." in ip.dalle_prompt


def test_bake_dialogue_leaves_silent_panels_clean():
    ip = ImagePrompt(
        panel_number=2,
        sd_prompt="wide establishing shot, empty street, cel shading, no text in image",
        dialogue=[],
    )
    bake_dialogue_into_prompts([ip])
    low = ip.sd_prompt.lower()
    # No dialogue → no bake-in instruction, and the silent panel isn't forced to
    # re-assert "no text" either (codex handles an empty panel fine).
    assert "balloon" not in low
    assert "empty street" in low


def test_bake_dialogue_skips_blank_bubble_text():
    ip = ImagePrompt(
        panel_number=3,
        sd_prompt="medium shot, two figures",
        dialogue=[
            {"speaker": "A", "type": "speech", "text": "   "},
            {"speaker": "B", "type": "speech", "text": "Chào cậu."},
        ],
    )
    bake_dialogue_into_prompts([ip])
    assert "Chào cậu." in ip.sd_prompt
    # The blank-text bubble for A contributes no line.
    assert ip.sd_prompt.count("draw ") == 1


def test_bake_dialogue_silent_panel_forbids_invented_lettering():
    """Silent panels must EXPLICITLY forbid lettering — otherwise Codex fills the
    empty panel by inventing English captions / sound-effects (the bug we saw:
    'AN ANCIENT BOTTLE', 'THE NORTH REMEMBERS BETRAYAL')."""
    ip = ImagePrompt(
        panel_number=4,
        sd_prompt="wide shot, ancient bottle on an altar, cel shading, no text in image",
        dialogue=[],
    )
    bake_dialogue_into_prompts([ip])
    low = ip.sd_prompt.lower()
    # Real content survives, the stripped clean-panel clause is gone...
    assert "ancient bottle on an altar" in low
    # ...and replaced by an explicit no-lettering guard naming the usual suspects.
    assert "captions" in low and "sound-effects" in low
    assert "free of lettering" in low
    # Still no instruction to DRAW a bubble on a silent panel.
    assert "balloon" not in low


def test_bake_dialogue_panel_forbids_extra_invented_text():
    """Dialogue panels must letter ONLY the listed bubbles — no extra invented
    captions/SFX beyond the verbatim VN lines."""
    ip = ImagePrompt(
        panel_number=5,
        sd_prompt="close-up, hero, cel shading, no text",
        dialogue=[{"speaker": "Lâm Phàm", "type": "speech", "text": "Ta sẽ trở lại."}],
    )
    bake_dialogue_into_prompts([ip])
    low = ip.sd_prompt.lower()
    assert "Ta sẽ trở lại." in ip.sd_prompt
    assert "only the caption boxes and bubbles listed above" in low
    assert "do not add any extra" in low


def test_bake_captions_letters_narration_box_with_bubbles():
    """Narration captions (thoại dẫn) must be baked as rectangular caption
    boxes alongside the bubbles — a comic without narration boxes loses the
    story thread between panels."""
    ip = ImagePrompt(
        panel_number=6,
        sd_prompt="wide shot, sect gate at dawn, cel shading, no text",
        captions=[{"type": "narration", "text": "Ba ngày sau, tại Thanh Vân Tông."}],
        dialogue=[{"speaker": "Kiên", "type": "speech", "text": "Ta đến rồi."}],
    )
    bake_dialogue_into_prompts([ip])
    low = ip.sd_prompt.lower()
    # Caption text verbatim, lettered as a tail-less rectangular box.
    assert "Ba ngày sau, tại Thanh Vân Tông." in ip.sd_prompt
    assert "rectangular caption box" in low
    assert "no tail" in low
    # Bubble still lettered too.
    assert "Ta đến rồi." in ip.sd_prompt
    assert ip.sd_prompt.count("containing exactly") == 2
    # dalle_prompt rewritten the same way.
    assert "Ba ngày sau, tại Thanh Vân Tông." in ip.dalle_prompt


def test_bake_caption_only_panel_letters_caption_not_silence_guard():
    """A panel with narration but no dialogue is NOT a silent panel — it must
    get the caption box, not the no-lettering guard."""
    ip = ImagePrompt(
        panel_number=7,
        sd_prompt="establishing shot, ruined village, cel shading, no text in image",
        captions=[{"type": "transition", "text": "Nửa năm trước, làng Đông Hà."}],
        dialogue=[],
    )
    bake_dialogue_into_prompts([ip])
    low = ip.sd_prompt.lower()
    assert "Nửa năm trước, làng Đông Hà." in ip.sd_prompt
    assert "rectangular caption box" in low
    # The silent-panel guard must NOT appear.
    assert "free of lettering" not in low
    # No speech balloon instruction for a dialogue-free panel.
    assert "balloon" not in low
