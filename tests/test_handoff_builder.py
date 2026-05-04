"""Tests for L1 handoff envelope builder + voice canonicalise shim + chapter-event mapping.

Sprint 1, Phase 2.
"""

from __future__ import annotations

import warnings
from types import SimpleNamespace

import pytest

from models.handoff_schemas import L1Handoff
from pipeline.layer1_story import _legacy_voice_aliases as aliases_mod
from pipeline.layer1_story._legacy_voice_aliases import canonicalise_voice_profile
from pipeline.layer1_story.chapter_contract_builder import (
    events_for_chapter,
    extract_chapter_num,
)
from pipeline.layer1_story.handoff_builder import build_l1_handoff


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _character(name: str, character_id: str | None = None):
    return SimpleNamespace(name=name, character_id=character_id or name.lower().replace(" ", "_"))


def _conflict(conflict_id: str, parties: list[str], ctype: str = "ideological", intensity: int = 3):
    return SimpleNamespace(
        conflict_id=conflict_id,
        characters=parties,
        conflict_type=ctype,
        intensity=intensity,
    )

    # `model_dump` not needed — handoff_builder accepts SimpleNamespace via dict() fallback


class _Conflict:
    def __init__(self, conflict_id, parties, ctype="ideological", intensity=3):
        self.conflict_id = conflict_id
        self.characters = parties
        self.conflict_type = ctype
        self.intensity = intensity

    def model_dump(self):
        return {
            "conflict_id": self.conflict_id,
            "characters": self.characters,
            "conflict_type": self.conflict_type,
            "intensity": self.intensity,
        }


class _Foreshadow:
    def __init__(self, hint, plant_chapter, payoff_chapter):
        self.hint = hint
        self.plant_chapter = plant_chapter
        self.payoff_chapter = payoff_chapter

    def model_dump(self):
        return {
            "hint": self.hint,
            "plant_chapter": self.plant_chapter,
            "payoff_chapter": self.payoff_chapter,
            "description": self.hint,
            "semantic_anchor": self.hint,
        }


class _Thread:
    def __init__(self, thread_id, description, planted_chapter, status="open"):
        self.thread_id = thread_id
        self.description = description
        self.planted_chapter = planted_chapter
        self.status = status

    def model_dump(self):
        return {
            "thread_id": self.thread_id,
            "description": self.description,
            "planted_chapter": self.planted_chapter,
            "status": self.status,
        }


def _full_draft():
    return SimpleNamespace(
        characters=[_character("Lý Huyền"), _character("Hoàng Yến")],
        outlines=[SimpleNamespace(chapter_number=i) for i in range(1, 11)],
        chapters=[],
        conflict_web=[
            _Conflict("c1", ["Lý Huyền", "Hoàng Yến"], "ideological", 4),
            _Conflict("c2", ["Lý Huyền"], "survival", 3),
        ],
        foreshadowing_plan=[_Foreshadow("Kiếm cổ phát sáng", 1, 8)],
        arc_waypoints=[
            {
                "character_name": "Lý Huyền",
                "chapter_range": [1, 5],
                "stage_name": "phủ nhận",
            }
        ],
        open_threads=[_Thread("t1", "Tìm sự thật về gia tộc", 1, "open")],
        voice_fingerprints=[
            {
                "name": "Lý Huyền",
                "verbal_tics": ["Hừ.", "Tiểu tử ngươi."],
                "dialogue_examples": ["Ta sẽ không lùi bước."],
                "register": "formal",
                "emotional_baseline": "kiên định",
            }
        ],
        voice_profiles=[],
    )


# ---------------------------------------------------------------------------
# canonicalise_voice_profile
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_alias_warned():
    aliases_mod._warned.clear()
    yield
    aliases_mod._warned.clear()


def test_canonicalise_maps_speech_quirks():
    raw = {"speech_quirks": ["Hừ.", "Tiểu tử ngươi."], "register": "formal"}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        out = canonicalise_voice_profile(raw)
    assert out["verbal_tics"] == ["Hừ.", "Tiểu tử ngươi."]
    assert "speech_quirks" not in out
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)


def test_canonicalise_maps_dialogue_example_singular():
    raw = {"dialogue_example": ["Ta đến rồi."], "register": "casual"}
    out = canonicalise_voice_profile(raw)
    assert out["dialogue_examples"] == ["Ta đến rồi."]
    assert "dialogue_example" not in out


def test_canonicalise_maps_dialogue_samples():
    raw = {"dialogue_samples": ["Hừm."], "register": "casual"}
    out = canonicalise_voice_profile(raw)
    assert out["dialogue_examples"] == ["Hừm."]


def test_canonicalise_idempotent():
    raw = {"speech_quirks": ["Hừ."], "register": "formal"}
    once = canonicalise_voice_profile(raw)
    twice = canonicalise_voice_profile(once)
    assert once == twice


def test_canonicalise_warns_only_once_per_alias():
    raw1 = {"speech_quirks": ["a"], "register": "formal"}
    raw2 = {"speech_quirks": ["b"], "register": "casual"}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        canonicalise_voice_profile(raw1)
        canonicalise_voice_profile(raw2)
    speech_quirks_warnings = [
        w for w in caught
        if issubclass(w.category, DeprecationWarning) and "speech_quirks" in str(w.message)
    ]
    assert len(speech_quirks_warnings) == 1


def test_canonicalise_does_not_mutate_input():
    raw = {"speech_quirks": ["Hừ."], "register": "formal"}
    canonicalise_voice_profile(raw)
    assert "speech_quirks" in raw  # original unchanged


def test_canonicalise_no_op_when_canonical_only():
    raw = {"verbal_tics": ["Hừ."], "register": "formal"}
    out = canonicalise_voice_profile(raw)
    assert out == raw


def test_canonicalise_drops_legacy_when_canonical_already_present():
    raw = {
        "verbal_tics": ["a"],
        "speech_quirks": ["b"],
        "register": "formal",
    }
    out = canonicalise_voice_profile(raw)
    assert out["verbal_tics"] == ["a"]
    assert "speech_quirks" not in out


# ---------------------------------------------------------------------------
# build_l1_handoff
# ---------------------------------------------------------------------------


def test_build_handoff_full_draft_all_ok():
    draft = _full_draft()
    env = build_l1_handoff(draft, story_id="story_001")
    assert isinstance(env, L1Handoff)
    assert env.story_id == "story_001"
    assert env.num_chapters == 10
    for name in ("conflict_web", "foreshadowing_plan", "arc_waypoints", "threads", "voice_fingerprints"):
        assert env.signal_health[name].status == "ok", f"{name} status: {env.signal_health[name]}"
    ok, blockers = env.is_usable_by_l2()
    assert ok is True
    assert blockers == []


def test_build_handoff_missing_conflict_web():
    draft = _full_draft()
    draft.conflict_web = None
    env = build_l1_handoff(draft, story_id="s1")
    assert env.signal_health["conflict_web"].status == "extraction_failed"


def test_build_handoff_empty_conflict_web():
    draft = _full_draft()
    draft.conflict_web = []
    env = build_l1_handoff(draft, story_id="s1")
    assert env.signal_health["conflict_web"].status == "empty"
    assert env.signal_health["conflict_web"].item_count == 0


def test_build_handoff_malformed_voice_profile():
    """Voice profile missing `register` → malformed status with last_error populated."""
    draft = _full_draft()
    draft.voice_fingerprints = [
        {
            "name": "Lý Huyền",
            "verbal_tics": ["Hừ."],
            "dialogue_examples": ["Test."],
            "emotional_baseline": "kiên định",
            # missing `register`
        }
    ]
    draft.voice_profiles = []
    env = build_l1_handoff(draft, story_id="s1")
    health = env.signal_health["voice_fingerprints"]
    assert health.status == "malformed"
    assert health.last_error is not None
    assert "register" in health.last_error


def test_build_handoff_legacy_alias_voice_profile_canonicalised():
    """Legacy `speech_quirks` should be canonicalised through to envelope."""
    draft = _full_draft()
    draft.voice_fingerprints = [
        {
            "name": "Lý Huyền",
            "speech_quirks": ["Hừ.", "Tiểu tử ngươi."],
            "dialogue_example": ["Ta đến rồi."],
            "register": "formal",
            "emotional_baseline": "kiên định",
        }
    ]
    draft.voice_profiles = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        env = build_l1_handoff(draft, story_id="s1")
    assert env.signal_health["voice_fingerprints"].status == "ok"
    fp = env.voice_fingerprints[0]
    assert fp.verbal_tics == ["Hừ.", "Tiểu tử ngươi."]
    assert fp.dialogue_examples == ["Ta đến rồi."]
    deprecation = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert len(deprecation) >= 1


def test_build_handoff_empty_voice_falls_back_to_voice_profiles():
    """When draft.voice_fingerprints is empty list, fall back to legacy `voice_profiles`."""
    draft = _full_draft()
    draft.voice_fingerprints = []
    draft.voice_profiles = [
        {
            "name": "Lý Huyền",
            "verbal_tics": ["Hừ."],
            "dialogue_examples": ["Ta đến rồi."],
            "register": "formal",
            "emotional_baseline": "kiên định",
        }
    ]
    env = build_l1_handoff(draft, story_id="s1")
    assert env.signal_health["voice_fingerprints"].status == "ok"
    assert env.voice_fingerprints[0].verbal_tics == ["Hừ."]


def test_build_handoff_threads_status_mapping():
    """Legacy `progressing` status should map to canonical `advancing`."""
    draft = _full_draft()
    draft.open_threads = [_Thread("t1", "Tìm sư phụ", 1, "progressing")]
    env = build_l1_handoff(draft, story_id="s1")
    assert env.threads[0].status == "advancing"


def test_build_handoff_arc_waypoint_uses_chapter_range_start():
    draft = _full_draft()
    env = build_l1_handoff(draft, story_id="s1")
    assert env.arc_waypoints[0].chapter == 1
    assert env.arc_waypoints[0].state_label == "phủ nhận"


# ---------------------------------------------------------------------------
# Chapter-event mapping fix
# ---------------------------------------------------------------------------


def test_extract_chapter_num_explicit_field():
    assert extract_chapter_num({"chapter": 3}) == 3
    assert extract_chapter_num({"chapter_number": 7}) == 7


def test_extract_chapter_num_tag_regex_no_substring_bug():
    """`ch1` must NOT match `ch10` / `ch11` etc. — exact regex extraction."""
    assert extract_chapter_num({"tag": "ch1"}) == 1
    assert extract_chapter_num({"tag": "ch_10"}) == 10
    assert extract_chapter_num({"tag": "ch-11"}) == 11
    # No regex match — return None rather than partial substring guess
    assert extract_chapter_num({"tag": "chương 3"}) is None


def test_extract_chapter_num_explicit_field_wins_over_tag():
    item = {"chapter": 5, "tag": "ch10"}
    assert extract_chapter_num(item) == 5


def test_events_for_chapter_excludes_higher_chapter_substring_matches():
    """11-chapter outline: chapter 1 events must NOT include ch10/ch11 events."""
    events = [
        {"id": "e1", "tag": "ch1"},
        {"id": "e10", "tag": "ch10"},
        {"id": "e11", "tag": "ch11"},
        {"id": "e12", "tag": "ch_1"},
        {"id": "e2", "chapter": 1},
        {"id": "e3", "chapter": 11},
    ]
    ch1 = events_for_chapter(events, 1)
    ids = {e["id"] for e in ch1}
    assert ids == {"e1", "e12", "e2"}
    assert "e10" not in ids
    assert "e11" not in ids


def test_events_for_chapter_simulationevent_like_object():
    """Object with `suggested_insertion` field — uses regex, not substring."""
    e1 = SimpleNamespace(suggested_insertion="ch1", id="e1")
    e10 = SimpleNamespace(suggested_insertion="ch10", id="e10")
    hits = events_for_chapter([e1, e10], 1)
    assert hits == [e1]
