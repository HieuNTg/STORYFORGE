"""Test ImagePromptGenerator service."""

import types

from models.schemas import Chapter
from services.image_prompt_generator import ImagePromptGenerator


def test_generate_scene_prompt_basic():
    gen = ImagePromptGenerator(style="cinematic")
    chapter = Chapter(
        chapter_number=1,
        title="The Beginning",
        content="Story content",
        summary="A hero emerges",
    )
    result = gen.generate_scene_prompt(chapter)
    assert result != ""
    assert "cinematic" in result


def test_generate_scene_prompt_uses_summary():
    gen = ImagePromptGenerator(style="anime")
    chapter = Chapter(
        chapter_number=1, title="Ch1", content="content", summary="battle scene"
    )
    result = gen.generate_scene_prompt(chapter)
    assert "battle scene" in result


def test_generate_scene_prompt_fallback_to_title():
    gen = ImagePromptGenerator(style="anime")
    chapter = Chapter(
        chapter_number=2, title="The Storm", content="content", summary=""
    )
    result = gen.generate_scene_prompt(chapter)
    assert "The Storm" in result


def test_default_style():
    gen = ImagePromptGenerator()
    assert gen.style != ""


# ---------------------------------------------------------------------------
# Phase 1: comic-panel prompt building (scene extractor + refiner)
# ---------------------------------------------------------------------------


from services.media.image_prompt_generator import _SCENE_EXTRACT_PROMPT


def _stub_llm(monkeypatch, gen, **methods):
    """Replace ``gen.llm`` wholesale instead of setattr-ing methods onto it.

    ``gen.llm`` is the process-wide LLMClient singleton: monkeypatching a
    method directly on it makes the undo write the old *bound method* into
    the instance ``__dict__``, permanently shadowing class-level patches in
    every later test (order-dependent failures).
    """
    monkeypatch.setattr(gen, "llm", types.SimpleNamespace(**methods))


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


# ---------------------------------------------------------------------------
# generate_from_shot_list — 1:1 panel-derived prompts (picture matches dialogue)
# ---------------------------------------------------------------------------

from services.media.shot_list import ShotList, Page, Panel


def _two_panel_shot_list():
    return ShotList(
        chapter_number=3,
        pages=[
            Page(
                page=1,
                panels=[
                    Panel(
                        n=1,
                        shot="WS",
                        beat="hoàng hôn ở làng",
                        subject="Kiên",
                        action="đứng giữa quảng trường",
                        setting="ngôi làng",
                        mood="u ám",
                    ),
                    Panel(
                        n=2,
                        shot="CU",
                        beat="mở Nghịch Mệnh Nhãn",
                        subject="Kiên",
                        action="mắt phát sáng nhìn sợi chỉ sinh mệnh",
                        setting="ngôi làng",
                        mood="kinh ngạc",
                    ),
                ],
            )
        ],
    )


def _shot_chapter():
    return Chapter(chapter_number=3, title="Tro tàn", content="Nội dung." * 50)


def test_generate_from_shot_list_one_prompt_per_panel_mapped_by_n(monkeypatch):
    """Every panel gets exactly one ImagePrompt, matched by the LLM's n field."""
    gen = ImagePromptGenerator(style="manhwa")

    def fake_generate_json(*a, **k):
        return {
            "prompts": [
                {
                    "n": 2,
                    "dalle_prompt": "close-up glowing eyes",
                    "sd_prompt": "cu eyes",
                },
                {
                    "n": 1,
                    "dalle_prompt": "wide shot village dusk",
                    "sd_prompt": "ws village",
                },
            ]
        }

    _stub_llm(monkeypatch, gen, generate_json=fake_generate_json)
    prompts = gen.generate_from_shot_list(_two_panel_shot_list(), _shot_chapter())

    assert len(prompts) == 2
    # Out-of-order LLM output is still mapped to the right panel by n.
    assert prompts[0].dalle_prompt == "wide shot village dusk"
    assert prompts[1].dalle_prompt == "close-up glowing eyes"
    assert prompts[0].panel_number == 1 and prompts[1].panel_number == 2
    assert prompts[0].chapter_number == 3
    assert prompts[0].scene_description == "hoàng hôn ở làng"


def test_generate_from_shot_list_fallback_for_skipped_panel(monkeypatch):
    """A panel the LLM skipped gets a deterministic fallback prompt built from
    its own fields — never a missing/empty prompt (compositor needs 1:1)."""
    gen = ImagePromptGenerator(style="manhwa")

    def fake_generate_json(*a, **k):
        return {
            "prompts": [
                {"n": 1, "dalle_prompt": "wide shot village", "sd_prompt": "ws"}
            ]
        }

    _stub_llm(monkeypatch, gen, generate_json=fake_generate_json)
    prompts = gen.generate_from_shot_list(_two_panel_shot_list(), _shot_chapter())

    assert len(prompts) == 2
    low = prompts[1].dalle_prompt.lower()
    assert "close-up" in low  # shot phrase from CU
    assert "mắt phát sáng nhìn sợi chỉ sinh mệnh" in prompts[1].dalle_prompt
    assert "no text in image" in low


def test_generate_from_shot_list_llm_failure_yields_all_fallbacks(monkeypatch):
    """A whole-call LLM failure still returns one fallback prompt per panel."""
    gen = ImagePromptGenerator(style="manhwa")

    def boom(*a, **k):
        raise RuntimeError("provider down")

    _stub_llm(monkeypatch, gen, generate_json=boom)
    prompts = gen.generate_from_shot_list(_two_panel_shot_list(), _shot_chapter())

    assert len(prompts) == 2
    for p in prompts:
        assert p.dalle_prompt and p.sd_prompt
        assert "comic panel" in p.dalle_prompt.lower()
        assert "manhwa" in p.dalle_prompt.lower()


def test_generate_from_shot_list_empty_when_no_panels():
    """No panels → [] so the handler falls back to the legacy chapter path."""
    gen = ImagePromptGenerator()
    empty = ShotList(chapter_number=3, pages=[])
    assert gen.generate_from_shot_list(empty, _shot_chapter()) == []


def test_generate_from_shot_list_uses_visual_profile_in_fallback(monkeypatch):
    """The frozen visual descriptor (not just the name) lands in fallback
    prompts so character consistency survives even the no-LLM path."""
    gen = ImagePromptGenerator(style="manhwa")

    def boom(*a, **k):
        raise RuntimeError("down")

    _stub_llm(monkeypatch, gen, generate_json=boom)
    prompts = gen.generate_from_shot_list(
        _two_panel_shot_list(),
        _shot_chapter(),
        visual_profiles={"Kiên": "thiếu niên tóc đen, áo vải xám, mắt đỏ"},
    )
    assert "thiếu niên tóc đen, áo vải xám, mắt đỏ" in prompts[0].dalle_prompt


def test_panel_prompt_template_demands_positive_constraints():
    """The panel prompt template must phrase constraints positively and ban
    in-image lettering (autoregressive image models ignore negative prompts)."""
    from services.media.image_prompt_generator import _PANEL_PROMPT_GEN

    low = _PANEL_PROMPT_GEN.lower()
    assert "no text in image" in low
    assert "no speech bubbles" in low


# ---------------------------------------------------------------------------
# Colour steering — comic prompts sit on the monochrome slice of the training
# data, so every builder must ask for colour explicitly.
# ---------------------------------------------------------------------------


def test_every_prompt_template_demands_colour():
    from services.media.image_prompt_generator import (
        _PANEL_PROMPT_GEN,
        _SCENE_EXTRACT_PROMPT,
    )

    for template in (_PANEL_PROMPT_GEN, _SCENE_EXTRACT_PROMPT):
        low = template.lower()
        assert "full color" in low
        assert "monochrome" in low


def test_fallback_panel_prompt_is_colour():
    from services.media._util import COLOR_CLAUSE

    gen = ImagePromptGenerator(style="manhwa comic panel")
    panel = types.SimpleNamespace(
        shot="MS",
        subject="Kiên",
        action="rút kiếm",
        setting="sân đình",
        mood="căng thẳng",
        beat="",
    )
    assert COLOR_CLAUSE in gen._fallback_panel_prompt(panel)


def test_shot_list_prompts_negate_monochrome(monkeypatch):
    """The negative prompt attached to every panel must fight grayscale too."""
    gen = ImagePromptGenerator(style="manhwa")
    monkeypatch.setattr(
        gen, "llm", types.SimpleNamespace(generate=lambda **kw: "not json")
    )
    prompts = gen.generate_from_shot_list(_two_panel_shot_list(), _shot_chapter())
    assert prompts
    for p in prompts:
        assert "monochrome" in p.negative_prompt
        assert "grayscale" in p.negative_prompt


def test_avatar_and_cover_prompts_are_colour():
    from models.schemas import ForgeCharacter
    from services.character_avatar import _build_avatar_prompt
    from services.cover_image import _build_cover_prompt
    from services.media._util import COLOR_CLAUSE

    char = ForgeCharacter(
        name="Kiên",
        role="protagonist",
        traits={"strength": 3, "wisdom": 3, "agility": 3, "scheme": 3},
        description="tóc đen",
        backstory="mồ côi",
        secret="mang huyết mạch cổ",
        conflict="báo thù",
    )
    avatar = _build_avatar_prompt(char, genre="Tiên Hiệp")
    cover = _build_cover_prompt("Truyện", "Tiên Hiệp", "tóm tắt")
    for prompt in (avatar, cover):
        assert COLOR_CLAUSE in prompt
        assert "NOT monochrome" in prompt
