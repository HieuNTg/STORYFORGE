"""Batch L, step L3: a character's picture follows the story.

A character who changes robes, loses an arm or wakes up with white hair used to
be drawn as their chapter-1 self forever: CharacterVisualProfileStore held one
frozen prompt and one reference image per character.

Forms live in the profile store beside that prompt and image (CEO decision
2026-09-14). The Library comic path only carries four character fields, so they
cannot travel on the Character model. They are derived from the chapter text at
comic time:

- one cheap call per chapter, cached by content hash;
- a change is accepted only when its quoted evidence appears verbatim in the
  chapter, so the check is deterministic;
- chapter N is drawn with the latest form whose from_chapter <= N;
- a form's reference image is derived once from the base reference (option B),
  falling back to prompt-only (option A) when that is not possible.
"""

from __future__ import annotations

import os
import types
from unittest.mock import MagicMock, patch

import pytest

from models.schemas import Chapter, Character, StoryDraft
from services.character_visual_profile import CharacterVisualProfileStore
from services.media import character_forms as cf

ROBE_EVIDENCE = "Diệp Lăng Thiên khoác lên mình bộ đạo bào trắng của Thiên Kiếm Tông."


@pytest.fixture
def store(tmp_path):
    s = CharacterVisualProfileStore(base_dir=str(tmp_path / "characters"))
    s.save_enhanced_profile("Diệp Lăng Thiên", "young swordsman", {}, "FP: black robe, topknot", "")
    s.save_enhanced_profile("Vân Tuyết Dao", "healer", {}, "FP: blue dress", "")
    return s


CHARS = [Character(name="Diệp Lăng Thiên", role="chính"), Character(name="Vân Tuyết Dao", role="phụ")]


def _chapters():
    return [
        Chapter(chapter_number=1, title="1", content="Diệp Lăng Thiên rời làng trong bộ áo đen."),
        Chapter(chapter_number=2, title="2", content=f"Sau buổi lễ, {ROBE_EVIDENCE} Hắn lặng im."),
        Chapter(chapter_number=3, title="3", content="Vân Tuyết Dao chữa thương cho hắn."),
    ]


class _LLM:
    """Answers the forms prompt; records which chapters were scanned."""

    def __init__(self, changes_by_chapter=None, fail_on=()):
        self.changes_by_chapter = changes_by_chapter or {}
        self.fail_on = set(fail_on)
        self.scanned: list[int] = []

    def generate_json(self, system_prompt="", user_prompt="", **kwargs):
        for chapter in _chapters():
            if chapter.content in user_prompt:
                n = chapter.chapter_number
                break
        else:  # content not found: a changed chapter
            n = int(user_prompt.split("CHƯƠNG ", 1)[1].split(":", 1)[0])
        self.scanned.append(n)
        if n in self.fail_on:
            raise RuntimeError("provider down")
        return {"changes": self.changes_by_chapter.get(n, [])}


ROBE_CHANGE = {
    2: [
        {
            "name": "Diệp Lăng Thiên",
            "description": "white Taoist robe of the Heavenly Sword Sect",
            "evidence": ROBE_EVIDENCE,
        }
    ]
}


# ── detection is gated by deterministic checks ──────────────────────────────


def test_change_with_verbatim_evidence_becomes_a_form(store):
    cf.ensure_forms(store, _LLM(ROBE_CHANGE), _chapters(), CHARS, upto_chapter=3)

    forms = store.get_forms("Diệp Lăng Thiên")
    assert [(f["from_chapter"], f["description"]) for f in forms] == [
        (2, "white Taoist robe of the Heavenly Sword Sect")
    ]
    assert store.get_forms("Vân Tuyết Dao") == []


def test_change_without_verbatim_evidence_is_rejected(store):
    invented = {2: [{**ROBE_CHANGE[2][0], "evidence": "Hắn thay áo mới."}]}

    cf.ensure_forms(store, _LLM(invented), _chapters(), CHARS, upto_chapter=3)

    assert store.get_forms("Diệp Lăng Thiên") == []


def test_change_for_unknown_character_is_rejected(store):
    stranger = {2: [{**ROBE_CHANGE[2][0], "name": "Người lạ"}]}

    cf.ensure_forms(store, _LLM(stranger), _chapters(), CHARS, upto_chapter=3)

    assert all(store.get_forms(c.name) == [] for c in CHARS)


@pytest.mark.parametrize(
    "description",
    [
        # Verbatim from a real run on a 10-chapter wuxia story: both passed the
        # evidence check, and the first would have drawn a character as a pile of
        # bones in any later panel he appears in.
        "body shattered into frozen black fragments, reduced to a pile of bones",
        "deceased, life force fully absorbed by the formation",
        "corpse lying on the altar",
    ],
)
def test_death_is_not_a_form(store, description):
    death = {2: [{**ROBE_CHANGE[2][0], "description": description}]}

    cf.ensure_forms(store, _LLM(death), _chapters(), CHARS, upto_chapter=3)

    assert store.get_forms("Diệp Lăng Thiên") == [], f"accepted as a look: {description!r}"


def test_forms_prompt_asks_for_the_resulting_look_and_excludes_death():
    prompt = cf._FORMS_PROMPT
    assert "chết" in prompt, "the prompt must rule out death"
    assert "ngoại hình KẾT QUẢ" in prompt, "description must be the look to draw from now on"


# ── scanning is cached by content ────────────────────────────────────────────


def test_each_chapter_is_scanned_once_per_content(store):
    llm = _LLM(ROBE_CHANGE)
    cf.ensure_forms(store, llm, _chapters(), CHARS, upto_chapter=3)
    cf.ensure_forms(store, llm, _chapters(), CHARS, upto_chapter=3)

    assert sorted(llm.scanned) == [1, 2, 3], "a chapter was scanned twice"


def test_only_chapters_up_to_the_target_are_scanned(store):
    llm = _LLM(ROBE_CHANGE)
    cf.ensure_forms(store, llm, _chapters(), CHARS, upto_chapter=2)

    assert sorted(llm.scanned) == [1, 2]


def test_rewritten_chapter_is_rescanned_and_its_old_forms_replaced(store):
    cf.ensure_forms(store, _LLM(ROBE_CHANGE), _chapters(), CHARS, upto_chapter=3)
    chapters = _chapters()
    chapters[1] = Chapter(chapter_number=2, title="2", content="CHƯƠNG 2: hắn vẫn mặc áo đen.")
    llm = _LLM({})

    cf.ensure_forms(store, llm, chapters, CHARS, upto_chapter=3)

    assert llm.scanned == [2]
    assert store.get_forms("Diệp Lăng Thiên") == []


def test_failed_scan_is_retried_next_time(store):
    cf.ensure_forms(store, _LLM(ROBE_CHANGE, fail_on={2}), _chapters(), CHARS, upto_chapter=3)
    llm = _LLM(ROBE_CHANGE)

    cf.ensure_forms(store, llm, _chapters(), CHARS, upto_chapter=3)

    assert llm.scanned == [2]
    assert len(store.get_forms("Diệp Lăng Thiên")) == 1


# ── selection by chapter ─────────────────────────────────────────────────────


def test_form_selection_by_chapter():
    forms = [
        {"from_chapter": 7, "description": "one-armed"},
        {"from_chapter": 3, "description": "white robe"},
    ]
    assert cf.form_for_chapter(forms, 2) is None
    assert cf.form_for_chapter(forms, 3)["description"] == "white robe"
    assert cf.form_for_chapter(forms, 6)["description"] == "white robe"
    assert cf.form_for_chapter(forms, 9)["description"] == "one-armed"


def test_for_chapter_appends_appearance_and_keeps_base_ref_without_form_ref():
    """Option A: no form reference yet — the base picture stays, the prompt changes."""
    forms_by_name = {"Diệp Lăng Thiên": [{"from_chapter": 2, "description": "white robe", "reference_image": ""}]}
    profiles = {"Diệp Lăng Thiên": "FP: black robe", "Vân Tuyết Dao": "FP: blue dress"}
    refs = {"Diệp Lăng Thiên": "/refs/base.png"}

    p1, r1 = cf.for_chapter(1, profiles, refs, forms_by_name)
    p2, r2 = cf.for_chapter(2, profiles, refs, forms_by_name)

    assert p1 == profiles and r1 == refs, "chapter 1 predates the change"
    assert p2["Diệp Lăng Thiên"].startswith("FP: black robe")
    assert "white robe" in p2["Diệp Lăng Thiên"]
    assert p2["Vân Tuyết Dao"] == "FP: blue dress"
    assert r2 == refs
    assert profiles["Diệp Lăng Thiên"] == "FP: black robe", "inputs must not be mutated"


def test_story_without_forms_renders_as_before():
    profiles, refs = {"A": "FP"}, {"A": "/r.png"}
    assert cf.for_chapter(5, profiles, refs, {}) == (profiles, refs)


def test_unreadable_forms_are_ignored():
    """The handler tests hand in MagicMock stores; garbage must not break images."""
    profiles, refs = {"A": "FP"}, {}
    assert cf.for_chapter(5, profiles, refs, {"A": MagicMock()}) == (profiles, refs)


# ── option B: a form's reference is derived once from the base reference ────


def test_form_reference_generated_once_from_base_reference(store, tmp_path):
    cf.ensure_forms(store, _LLM(ROBE_CHANGE), _chapters(), CHARS, upto_chapter=3)
    base = tmp_path / "base.png"
    base.write_bytes(b"png")
    made = tmp_path / "form.png"

    image_gen = types.SimpleNamespace(calls=[])

    def generate_with_reference(prompt, reference_paths, filename="", size=""):
        image_gen.calls.append((prompt, list(reference_paths), filename))
        made.write_bytes(b"png")
        return str(made)

    image_gen.generate_with_reference = generate_with_reference
    refs = {"Diệp Lăng Thiên": str(base)}
    profiles = {"Diệp Lăng Thiên": "FP: black robe"}

    first = cf.prepare_form_references(store, CHARS, profiles, refs, image_gen, provider="qwen-local")
    second = cf.prepare_form_references(store, CHARS, profiles, refs, image_gen, provider="qwen-local")

    assert len(image_gen.calls) == 1, "the form reference was rendered twice"
    prompt, sources, _ = image_gen.calls[0]
    assert sources == [str(base)]
    assert "white Taoist robe" in prompt
    assert first["Diệp Lăng Thiên"][0]["reference_image"] == str(made)
    assert second == first
    _, r2 = cf.for_chapter(2, profiles, refs, first)
    assert r2["Diệp Lăng Thiên"] == str(made)


def test_provider_without_reference_support_falls_back_to_prompt_only(store, tmp_path):
    cf.ensure_forms(store, _LLM(ROBE_CHANGE), _chapters(), CHARS, upto_chapter=3)
    image_gen = MagicMock()
    refs = {"Diệp Lăng Thiên": str(tmp_path / "base.png")}

    forms = cf.prepare_form_references(store, CHARS, {}, refs, image_gen, provider="dalle")

    image_gen.generate_with_reference.assert_not_called()
    assert forms["Diệp Lăng Thiên"][0]["reference_image"] == ""


# ── the live comic path uses it ──────────────────────────────────────────────


def test_handler_draws_each_chapter_with_its_own_form(store):
    from config import ConfigManager
    from services.handlers import handle_generate_images

    draft = StoryDraft(title="Đế Tôn", genre="Tiên hiệp", synopsis="", characters=CHARS, chapters=_chapters())
    orch = types.SimpleNamespace(
        output=types.SimpleNamespace(enhanced_story=None, story_draft=draft), session_id="s1"
    )
    cfg = ConfigManager().pipeline
    saved = (cfg.comic_shot_list_enabled, getattr(cfg, "comic_character_forms_enabled", None))
    cfg.comic_shot_list_enabled = False
    cfg.comic_character_forms_enabled = True
    try:
        with (
            patch("services.image_generator.ImageGenerator") as MockImgGen,
            patch("services.image_prompt_generator.ImagePromptGenerator") as MockPromptGen,
            patch("services.character_visual_profile.CharacterVisualProfileStore", return_value=store),
            patch("services.media.character_forms.LLMClient", return_value=_LLM(ROBE_CHANGE)),
        ):
            MockImgGen.return_value.output_dir = "out/images"
            MockImgGen.return_value.generate_story_images.return_value = ["img.png"]
            MockPromptGen.return_value.generate_from_chapter.return_value = [MagicMock()]

            handle_generate_images(orch, provider="dalle", t=None)

            seen = {
                kwargs["chapter"].chapter_number if "chapter" in kwargs else args[0].chapter_number: kwargs.get(
                    "visual_profiles"
                )
                for args, kwargs in MockPromptGen.return_value.generate_from_chapter.call_args_list
            }
    finally:
        cfg.comic_shot_list_enabled = saved[0]
        if saved[1] is None:
            delattr(cfg, "comic_character_forms_enabled")
        else:
            cfg.comic_character_forms_enabled = saved[1]

    assert "white Taoist robe" not in (seen[1] or {}).get("Diệp Lăng Thiên", "")
    assert "white Taoist robe" in seen[2]["Diệp Lăng Thiên"]
    assert "white Taoist robe" in seen[3]["Diệp Lăng Thiên"]


def test_forms_flag_exists_and_defaults_on():
    from config.defaults import PipelineConfig

    assert PipelineConfig().comic_character_forms_enabled is True
    assert os.path  # keep import used


def test_rebuilding_the_base_profile_keeps_forms(store):
    cf.ensure_forms(store, _LLM(ROBE_CHANGE), _chapters(), CHARS, upto_chapter=3)

    store.save_enhanced_profile("Diệp Lăng Thiên", "young swordsman", {}, "FP: rebuilt", "")

    assert len(store.get_forms("Diệp Lăng Thiên")) == 1, "a profile rebuild erased the character's forms"
