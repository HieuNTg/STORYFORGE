"""Phase 2 — Beat→Shot-list extractor tests (spec §7).

Asserts the deterministic post-processing rules on top of (mocked) LLM output:
  - no two adjacent panels share the same shot
  - ≤2 bubbles per panel; long speaker splits into a new panel
  - a new scene opens with an establishing shot (EWS/WS)
  - the largest beat is assigned its own SPLASH page
  - Vietnamese dialogue round-trips byte-for-byte (diacritics preserved)

The LLM is mocked (no real provider) following the existing convention of
monkeypatching ``<obj>.llm`` (see tests/test_image_prompt_gen.py).
"""
from models.schemas import Chapter, ImagePrompt
from services.media.shot_list import (
    ShotListExtractor,
    ShotList,
    Page,
    Panel,
    Bubble,
    Caption,
    enforce_rules,
    apply_shot_list_to_prompts,
    extract_shot_list,
)


# Vietnamese dialogue with the full diacritic battery from the spec brief.
VI_LINE_1 = "Cậu... cậu là người sống sót cuối cùng sao?"
VI_LINE_2 = "Không. Ta là kẻ sẽ báo thù — ữ ạ ọ ậ ỹ ề."
VI_CAPTION = "Làng Đông đã không còn."


def _raw_pages(panels):
    """Wrap a list of panel dicts into the raw LLM ``{"pages": [...]}`` shape."""
    return {"pages": [{"page": 1, "layout": "THREE_TIER", "panels": panels}]}


def _make_extractor(monkeypatch, raw_response):
    """Build a ShotListExtractor whose LLM returns ``raw_response`` verbatim."""
    extractor = ShotListExtractor()

    def fake_generate_json(*args, **kwargs):
        return raw_response

    monkeypatch.setattr(extractor.llm, "generate_json", fake_generate_json, raising=False)
    return extractor


def _chapter():
    return Chapter(chapter_number=3, title="Tro tàn", content="Một chương dài." * 50)


# ---------------------------------------------------------------------------
# enforce_rules — pure deterministic post-processing (no LLM)
# ---------------------------------------------------------------------------
def test_no_two_adjacent_shots_identical():
    """Adjacent panels must never share the same shot after enforcement."""
    sl = ShotList(chapter_number=1, pages=[Page(panels=[
        Panel(n=1, shot="MS", setting="cùng cảnh", beat="a"),
        Panel(n=2, shot="MS", setting="cùng cảnh", beat="b"),
        Panel(n=3, shot="MS", setting="cùng cảnh", beat="c"),
        Panel(n=4, shot="MS", setting="cùng cảnh", beat="d"),
    ])])
    out = enforce_rules(sl)
    panels = out.all_panels()
    for i in range(1, len(panels)):
        assert panels[i].shot != panels[i - 1].shot, (
            f"panel {i} shot {panels[i].shot} == prev"
        )


def test_at_most_two_bubbles_per_panel():
    """A panel with >2 bubbles is split so every panel has ≤2."""
    sl = ShotList(chapter_number=1, pages=[Page(panels=[
        Panel(n=1, shot="MS", setting="phòng", beat="talk", bubbles=[
            Bubble(speaker="A", text="một"),
            Bubble(speaker="B", text="hai"),
            Bubble(speaker="A", text="ba"),
            Bubble(speaker="B", text="bốn"),
        ]),
    ])])
    out = enforce_rules(sl)
    for p in out.all_panels():
        assert len(p.bubbles) <= 2


def test_long_speaker_splits_into_new_panel():
    """A speaker with > ~20 Vietnamese words is moved into a new panel."""
    long_line = " ".join(f"từ{i}" for i in range(30))  # 30 words
    sl = ShotList(chapter_number=1, pages=[Page(panels=[
        Panel(n=1, shot="MS", setting="phòng", beat="talk", bubbles=[
            Bubble(speaker="A", text="ngắn"),
            Bubble(speaker="B", text=long_line),
        ]),
    ])])
    out = enforce_rules(sl)
    panels = out.all_panels()
    # The short and long lines now live in separate panels.
    assert len(panels) >= 2
    texts = [b.text for p in panels for b in p.bubbles]
    assert "ngắn" in texts
    assert long_line in texts
    # No panel holds both.
    for p in panels:
        assert not ("ngắn" in [b.text for b in p.bubbles]
                    and long_line in [b.text for b in p.bubbles])


def test_new_scene_opens_with_establishing_shot():
    """The first panel of a new scene (setting change) becomes EWS/WS."""
    sl = ShotList(chapter_number=1, pages=[Page(panels=[
        Panel(n=1, shot="CU", setting="ngôi làng", beat="open"),
        Panel(n=2, shot="MS", setting="ngôi làng", beat="react"),
        # setting changes here → new scene → must become establishing
        Panel(n=3, shot="CU", setting="khu rừng", beat="move"),
    ])])
    out = enforce_rules(sl)
    panels = out.all_panels()
    # Panel 0 (very first) is a scene start too.
    assert panels[0].shot in ("EWS", "WS")
    # The panel that changed setting must be establishing.
    rebuilt = {p.setting: p for p in panels}
    assert rebuilt["khu rừng"].shot in ("EWS", "WS")


def test_new_scene_gets_transition_caption_on_change():
    """A location change on a non-first panel adds a transition caption."""
    sl = ShotList(chapter_number=1, pages=[Page(panels=[
        Panel(n=1, shot="EWS", setting="ngôi làng", beat="open"),
        Panel(n=2, shot="CU", setting="khu rừng", beat="elsewhere"),
    ])])
    out = enforce_rules(sl)
    forest = next(p for p in out.all_panels() if p.setting == "khu rừng")
    assert forest.captions, "expected a transition caption on scene change"
    assert any(c.text == "khu rừng" for c in forest.captions)


def test_splash_assigned_to_largest_beat():
    """The biggest beat (most dialogue/description) gets its own SPLASH page."""
    big_dialogue = [Bubble(speaker="K", text="x" * 200)]
    sl = ShotList(chapter_number=1, pages=[Page(panels=[
        Panel(n=1, shot="EWS", setting="a", beat="small"),
        Panel(n=2, shot="MS", setting="a", beat="THE BIG REVEAL with lots of weight",
              action="x" * 100, mood="y" * 50, bubbles=big_dialogue),
        Panel(n=3, shot="CU", setting="a", beat="small2"),
    ])])
    out = enforce_rules(sl)
    splash_pages = [pg for pg in out.pages if pg.layout == "SPLASH"]
    assert len(splash_pages) == 1
    assert len(splash_pages[0].panels) == 1
    # The splash panel is the heavy one carrying the big dialogue.
    splash_panel = splash_pages[0].panels[0]
    assert splash_panel.bubbles and len(splash_panel.bubbles[0].text) == 200


def test_subject_resolves_to_character_reference():
    """Each subject is bound to its saved character reference path."""
    sl = ShotList(chapter_number=1, pages=[Page(panels=[
        Panel(n=1, shot="EWS", setting="a", subject="Kiên", beat="b"),
        Panel(n=2, shot="MS", setting="a", subject="Bà lão", beat="c"),
    ])])
    refs = {"Kiên": "/refs/kien.png", "Bà lão": "/refs/balao.png"}
    out = enforce_rules(sl, character_references=refs)
    by_subject = {p.subject: p for p in out.all_panels()}
    assert by_subject["Kiên"].subject_ref == "/refs/kien.png"
    assert by_subject["Bà lão"].subject_ref == "/refs/balao.png"


def test_vietnamese_dialogue_roundtrips_byte_for_byte():
    """Diacritics in bubbles and captions survive enforcement unchanged."""
    sl = ShotList(chapter_number=1, pages=[Page(panels=[
        Panel(n=1, shot="EWS", setting="làng", beat="open",
              captions=[Caption(type="narration", text=VI_CAPTION)]),
        Panel(n=2, shot="MS", setting="làng", beat="plead",
              bubbles=[Bubble(speaker="Bà lão", text=VI_LINE_1)]),
        Panel(n=3, shot="CU", setting="làng", beat="resolve",
              bubbles=[Bubble(speaker="Kiên", text=VI_LINE_2)]),
    ])])
    out = enforce_rules(sl)
    all_text = [b.text for p in out.all_panels() for b in p.bubbles]
    all_caps = [c.text for p in out.all_panels() for c in p.captions]
    assert VI_LINE_1 in all_text
    assert VI_LINE_2 in all_text
    assert VI_CAPTION in all_caps


# ---------------------------------------------------------------------------
# ShotListExtractor — end-to-end with a mocked LLM
# ---------------------------------------------------------------------------
def test_extractor_end_to_end_mocked_llm(monkeypatch):
    """Full extract path: mocked LLM JSON → parsed → rules enforced."""
    raw = _raw_pages([
        {"n": 1, "shot": "CU", "beat": "establish", "subject": "Kiên",
         "setting": "ngôi làng", "screen_side": {"Kiên": "center"},
         "captions": [{"type": "narration", "text": VI_CAPTION}], "bubbles": []},
        {"n": 2, "shot": "CU", "beat": "plead", "subject": "Bà lão",
         "setting": "ngôi làng", "screen_side": {"Bà lão": "left", "Kiên": "right"},
         "bubbles": [{"speaker": "Bà lão", "type": "speech", "text": VI_LINE_1}]},
        {"n": 3, "shot": "CU", "beat": "resolve", "subject": "Kiên",
         "setting": "ngôi làng", "screen_side": {"Kiên": "right"},
         "bubbles": [{"speaker": "Kiên", "type": "speech", "text": VI_LINE_2}]},
    ])
    extractor = _make_extractor(monkeypatch, raw)
    sl = extractor.extract(_chapter(), character_references={"Kiên": "/r/k.png"})

    panels = sl.all_panels()
    assert panels, "expected non-empty shot-list"
    # First panel of the chapter (new scene) is establishing.
    assert panels[0].shot in ("EWS", "WS")
    # No adjacent duplicate shots.
    for i in range(1, len(panels)):
        assert panels[i].shot != panels[i - 1].shot
    # Vietnamese preserved.
    all_text = [b.text for p in panels for b in p.bubbles]
    assert VI_LINE_1 in all_text and VI_LINE_2 in all_text
    # Subject ref resolved.
    assert any(p.subject_ref == "/r/k.png" for p in panels if p.subject == "Kiên")


def test_extractor_returns_empty_on_llm_failure(monkeypatch):
    """If the LLM raises, the extractor degrades to an empty shot-list."""
    extractor = ShotListExtractor()

    def boom(*a, **k):
        raise RuntimeError("provider down")

    monkeypatch.setattr(extractor.llm, "generate_json", boom, raising=False)
    sl = extractor.extract(_chapter())
    assert sl.pages == []


def test_module_level_extract_shot_list(monkeypatch):
    """The convenience wrapper threads through to ShotListExtractor."""
    raw = _raw_pages([
        {"n": 1, "shot": "WS", "beat": "b", "subject": "Kiên", "setting": "x"},
    ])
    monkeypatch.setattr(
        "services.media.shot_list.ShotListExtractor.extract",
        lambda self, *a, **k: ShotList(chapter_number=9, pages=[
            Page(panels=[Panel(n=1, shot="WS", subject="Kiên")])
        ]),
    )
    sl = extract_shot_list(_chapter())
    assert sl.chapter_number == 9


# ---------------------------------------------------------------------------
# apply_shot_list_to_prompts — threading metadata onto ImagePrompt
# ---------------------------------------------------------------------------
def test_apply_shot_list_to_prompts_threads_metadata():
    """shot_type / dialogue / screen_side land on the ImagePrompt; text stays out
    of the prompt strings (image prompts carry NO dialogue)."""
    prompts = [
        ImagePrompt(panel_number=1, dalle_prompt="P1", sd_prompt="S1"),
        ImagePrompt(panel_number=2, dalle_prompt="P2", sd_prompt="S2"),
    ]
    sl = ShotList(chapter_number=1, pages=[Page(panels=[
        Panel(n=1, shot="EWS", screen_side={"Kiên": "center"}, bubbles=[]),
        Panel(n=2, shot="MS", screen_side={"Bà lão": "left"},
              bubbles=[Bubble(speaker="Bà lão", type="speech", text=VI_LINE_1)]),
    ])])
    apply_shot_list_to_prompts(prompts, sl)

    assert prompts[0].shot_type == "EWS"
    assert prompts[1].shot_type == "MS"
    assert prompts[1].dialogue == [
        {"speaker": "Bà lão", "type": "speech", "text": VI_LINE_1}
    ]
    assert prompts[1].screen_side == {"Bà lão": "left"}
    # Image prompt strings must remain free of dialogue text.
    assert VI_LINE_1 not in prompts[1].dalle_prompt
    assert VI_LINE_1 not in prompts[1].sd_prompt
