"""Phase 2 — Beat→Shot-list extractor tests (spec §7).

Asserts the deterministic post-processing rules on top of (mocked) LLM output:
  - no two adjacent panels share the same shot
  - ≤2 bubbles per panel; long speaker splits into a new panel
  - a new scene opens with an establishing shot (EWS/WS)
  - the largest beat is assigned its own SPLASH page
  - Vietnamese dialogue round-trips byte-for-byte (diacritics preserved)

The LLM is mocked (no real provider) by replacing ``<obj>.llm`` wholesale —
``<obj>.llm`` is the process-wide LLMClient singleton, so setattr-ing methods
onto it leaks bound-method shadows into its ``__dict__`` on monkeypatch undo
(see tests/test_image_prompt_gen.py).
"""
import types

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

    monkeypatch.setattr(extractor, "llm", types.SimpleNamespace(generate_json=fake_generate_json))
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

    monkeypatch.setattr(extractor, "llm", types.SimpleNamespace(generate_json=boom))
    sl = extractor.extract(_chapter())
    assert sl.pages == []


def test_module_level_extract_shot_list(monkeypatch):
    """The convenience wrapper threads through to ShotListExtractor."""
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


# ---------------------------------------------------------------------------
# Coverage check — second verifier pass inserts dropped beats
# ---------------------------------------------------------------------------
def _make_coverage_extractor(monkeypatch, pass1_raw, pass2_raw):
    """Extractor whose LLM answers pass-1 (pages) and pass-2 (missing) in turn.

    Calls are told apart by ``list_key`` (extract uses "pages", the verifier
    uses "missing") so the test doesn't depend on call ordering details.
    ``pass2_raw`` may be an Exception instance to simulate verifier failure.
    Returns (extractor, calls) where calls records each list_key seen.
    """
    extractor = ShotListExtractor()
    calls = []

    def fake_generate_json(*args, **kwargs):
        key = kwargs.get("list_key")
        calls.append(key)
        if key == "missing":
            if isinstance(pass2_raw, Exception):
                raise pass2_raw
            return pass2_raw
        return pass1_raw

    monkeypatch.setattr(extractor, "llm", types.SimpleNamespace(generate_json=fake_generate_json))
    return extractor, calls


_PASS1 = None  # built lazily so each test gets fresh dicts


def _pass1_three_beats():
    return _raw_pages([
        {"n": 1, "shot": "WS", "beat": "hoàng hôn ở làng", "subject": "Kiên",
         "setting": "ngôi làng", "bubbles": []},
        {"n": 2, "shot": "MS", "beat": "đối thoại với bà lão", "subject": "Bà lão",
         "setting": "ngôi làng",
         "bubbles": [{"speaker": "Bà lão", "type": "speech", "text": VI_LINE_1}]},
        {"n": 3, "shot": "CU", "beat": "quyết tâm báo thù", "subject": "Kiên",
         "setting": "ngôi làng", "bubbles": []},
    ])


def test_coverage_check_inserts_missing_beat_after_anchor(monkeypatch):
    """The verifier's missing beat is inserted right after its anchor panel."""
    pass2 = {"missing": [
        {"after_panel": 1, "shot": "INSERT", "beat": "cuốn sổ của cha",
         "subject": "Kiên", "setting": "ngôi làng",
         "action": "mở cuốn sổ ghi nợ tuổi thọ", "bubbles": []},
    ]}
    extractor, calls = _make_coverage_extractor(monkeypatch, _pass1_three_beats(), pass2)
    sl = extractor.extract(_chapter(), coverage_check=True)

    assert calls.count("pages") == 1 and calls.count("missing") == 1
    beats = [p.beat for p in sl.all_panels()]
    assert "cuốn sổ của cha" in beats
    # Inserted beat sits after its anchor (#1) and before the old #2.
    assert beats.index("cuốn sổ của cha") > beats.index("hoàng hôn ở làng")
    assert beats.index("cuốn sổ của cha") < beats.index("đối thoại với bà lão")
    assert len(beats) == 4


def test_coverage_check_anchor_zero_inserts_before_first(monkeypatch):
    """after_panel=0 means the missing beat opens the chapter."""
    pass2 = {"missing": [
        {"after_panel": 0, "shot": "EWS", "beat": "toàn cảnh thôn trước biến cố",
         "subject": "Kiên", "setting": "ngôi làng", "bubbles": []},
    ]}
    extractor, _ = _make_coverage_extractor(monkeypatch, _pass1_three_beats(), pass2)
    sl = extractor.extract(_chapter(), coverage_check=True)
    beats = [p.beat for p in sl.all_panels()]
    assert beats[0] == "toàn cảnh thôn trước biến cố"


def test_coverage_check_off_makes_single_llm_call(monkeypatch):
    """coverage_check=False (the default) must not call the verifier."""
    extractor, calls = _make_coverage_extractor(
        monkeypatch, _pass1_three_beats(), {"missing": []}
    )
    sl = extractor.extract(_chapter())
    assert sl.all_panels()
    assert calls == ["pages"]


def test_coverage_check_no_missing_keeps_panels_unchanged(monkeypatch):
    """An all-covered verdict leaves the beat list as-is."""
    extractor, calls = _make_coverage_extractor(
        monkeypatch, _pass1_three_beats(), {"missing": []}
    )
    sl = extractor.extract(_chapter(), coverage_check=True)
    assert calls.count("missing") == 1
    assert len(sl.all_panels()) == 3


def test_coverage_check_verifier_failure_degrades_to_unverified(monkeypatch):
    """A verifier crash must NOT lose the pass-1 shot-list."""
    extractor, _ = _make_coverage_extractor(
        monkeypatch, _pass1_three_beats(), RuntimeError("verifier down")
    )
    sl = extractor.extract(_chapter(), coverage_check=True)
    assert len(sl.all_panels()) == 3


def test_coverage_check_caps_inserts(monkeypatch):
    """A runaway verifier is capped at MAX_COVERAGE_INSERTS insertions."""
    from services.media.shot_list import MAX_COVERAGE_INSERTS
    pass2 = {"missing": [
        {"after_panel": 1, "shot": "INSERT", "beat": f"thừa {i}",
         "subject": "Kiên", "setting": "ngôi làng", "bubbles": []}
        for i in range(MAX_COVERAGE_INSERTS + 5)
    ]}
    extractor, _ = _make_coverage_extractor(monkeypatch, _pass1_three_beats(), pass2)
    sl = extractor.extract(_chapter(), coverage_check=True)
    assert len(sl.all_panels()) == 3 + MAX_COVERAGE_INSERTS


def test_coverage_check_clamps_out_of_range_anchor(monkeypatch):
    """An anchor beyond the last beat clamps to the end instead of crashing."""
    pass2 = {"missing": [
        {"after_panel": 99, "shot": "CU", "beat": "đoạn kết bị sót",
         "subject": "Kiên", "setting": "ngôi làng", "bubbles": []},
    ]}
    extractor, _ = _make_coverage_extractor(monkeypatch, _pass1_three_beats(), pass2)
    sl = extractor.extract(_chapter(), coverage_check=True)
    beats = [p.beat for p in sl.all_panels()]
    assert beats[-1] == "đoạn kết bị sót"


def test_apply_shot_list_to_prompts_threads_captions():
    """Narration captions must travel onto the ImagePrompt too — the Codex bake
    step letters them as caption boxes; dropping them here was why comics came
    out with zero 'thoại dẫn' (reader couldn't follow the story)."""
    prompts = [ImagePrompt(panel_number=1, dalle_prompt="P1", sd_prompt="S1")]
    sl = ShotList(chapter_number=1, pages=[Page(panels=[
        Panel(n=1, shot="EWS",
              captions=[Caption(type="narration",
                                text="Ba ngày sau, tại Thanh Vân Tông.")],
              bubbles=[]),
    ])])
    apply_shot_list_to_prompts(prompts, sl)
    assert prompts[0].captions == [
        {"type": "narration", "text": "Ba ngày sau, tại Thanh Vân Tông."}
    ]
