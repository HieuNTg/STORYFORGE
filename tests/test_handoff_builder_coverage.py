"""Coverage push for `pipeline.layer1_story.handoff_builder` (Sprint 1, Phase 7).

Targets uncovered branches in the existing builder:
- extraction sentinel ({"_error": ...}) for every signal
- non-list raw input for every signal
- partial-failure (some entries valid, some rejected) producing ``ok`` health
  with ``last_error`` populated
- foreshadowing fallback id generation when seed dict missing ``id``
- threads ``resolution_chapter`` + ``involved_characters`` aliases
- voice fingerprint optional-field projection (``emotional_expression`` dict
  vs string, ``avg_sentence_length`` parse failure, ``vocabulary_level``
  fallback to ``register``)
"""

from __future__ import annotations

from types import SimpleNamespace

from models.handoff_schemas import L1Handoff
from pipeline.layer1_story.handoff_builder import (
    _build_arc_waypoints,
    _build_conflict_web,
    _build_foreshadowing,
    _build_threads,
    _build_voice_fingerprints,
    build_l1_handoff,
)


# ---------------------------------------------------------------------------
# Extraction sentinel — produced upstream when an extractor failed
# ---------------------------------------------------------------------------

def test_conflict_web_sentinel_marks_extraction_failed():
    web, health = _build_conflict_web({"_error": "LLM 500"})
    assert health.status == "extraction_failed"
    assert health.last_error == "LLM 500"
    assert web.nodes == []


def test_foreshadowing_sentinel_marks_extraction_failed():
    seeds, health = _build_foreshadowing({"_error": "timeout"})
    assert health.status == "extraction_failed"
    assert health.last_error == "timeout"
    assert seeds == []


def test_arc_waypoints_sentinel_marks_extraction_failed():
    wps, health = _build_arc_waypoints({"_error": "parse fail"}, {})
    assert health.status == "extraction_failed"
    assert health.last_error == "parse fail"
    assert wps == []


def test_threads_sentinel_marks_extraction_failed():
    threads, health = _build_threads({"_error": "x"})
    assert health.status == "extraction_failed"
    assert health.last_error == "x"
    assert threads == []


def test_voice_sentinel_marks_extraction_failed():
    fps, health = _build_voice_fingerprints({"_error": "y"}, {})
    assert health.status == "extraction_failed"
    assert health.last_error == "y"
    assert fps == []


# ---------------------------------------------------------------------------
# Wrong type — not a list → malformed
# ---------------------------------------------------------------------------

def test_conflict_web_string_input_marks_malformed():
    web, health = _build_conflict_web("not a list")
    assert health.status == "malformed"
    assert "str" in health.reason
    assert web.nodes == []


def test_foreshadowing_dict_input_marks_malformed():
    seeds, health = _build_foreshadowing({"f1": "x"})  # plain dict, not sentinel
    assert health.status == "malformed"
    assert "dict" in health.reason
    assert seeds == []


def test_arc_waypoints_int_input_marks_malformed():
    wps, health = _build_arc_waypoints(42, {})
    assert health.status == "malformed"
    assert "int" in health.reason


def test_threads_string_input_marks_malformed():
    threads, health = _build_threads("oops")
    assert health.status == "malformed"
    assert "str" in health.reason


def test_voice_string_input_marks_malformed():
    fps, health = _build_voice_fingerprints("oops", {})
    assert health.status == "malformed"


# ---------------------------------------------------------------------------
# Partial failure — some entries valid, others rejected → status=ok with
# last_error populated and 'some entries dropped' reason
# ---------------------------------------------------------------------------

def test_conflict_web_partial_failure_keeps_valid_entries():
    raw = [
        {"conflict_id": "c1", "characters": ["A", "B"], "conflict_type": "power", "intensity": 3},
        # `intensity=99` will be clamped to 5 (so this still passes)
        # Use a malformed entry instead — non-iterable parties triggers TypeError
        {"conflict_id": "c2", "characters": object(), "conflict_type": "power", "intensity": 2},
    ]
    web, health = _build_conflict_web(raw)
    # First entry succeeds, second is rejected — health stays "ok" with error noted
    assert health.status == "ok"
    assert health.item_count == 1
    assert health.last_error is not None
    assert health.reason == "some entries dropped"
    assert len(web.nodes) == 1


def test_conflict_web_intensity_clamped_to_bounds():
    """`intensity=99` clamps to 5; `intensity=0` clamps to 1."""
    raw = [
        {"conflict_id": "c_high", "characters": ["A"], "conflict_type": "power", "intensity": 99},
        {"conflict_id": "c_low", "characters": ["B"], "conflict_type": "power", "intensity": -5},
    ]
    web, health = _build_conflict_web(raw)
    assert health.status == "ok"
    assert health.item_count == 2
    assert web.nodes[0].intensity == 5
    assert web.nodes[1].intensity == 1


def test_conflict_web_all_entries_rejected_marks_malformed():
    raw = [
        {"conflict_id": "c1", "characters": object(), "conflict_type": "power", "intensity": 3},
    ]
    web, health = _build_conflict_web(raw)
    assert health.status == "malformed"
    assert health.last_error is not None


def test_foreshadowing_missing_plant_chapter_rejected():
    raw = [
        {"id": "f_bad", "payoff_chapter": 5, "description": "no plant"},
        {"id": "f_good", "plant_chapter": 1, "payoff_chapter": 6, "description": "ok"},
    ]
    seeds, health = _build_foreshadowing(raw)
    assert health.status == "ok"
    assert health.item_count == 1
    assert seeds[0].id == "f_good"
    assert health.last_error is not None


def test_foreshadowing_default_id_when_missing():
    raw = [{"plant_chapter": 1, "payoff_chapter": 5, "description": "anon", "semantic_anchor": "x"}]
    seeds, _ = _build_foreshadowing(raw)
    assert seeds[0].id == "f1"


def test_foreshadowing_all_entries_rejected_marks_malformed():
    raw = [{"id": "bad", "plant_chapter": "not-an-int", "payoff_chapter": 5, "description": "x"}]
    seeds, health = _build_foreshadowing(raw)
    assert health.status == "malformed"
    assert seeds == []


# ---------------------------------------------------------------------------
# arc_waypoints alternative input shapes
# ---------------------------------------------------------------------------

def test_arc_waypoint_uses_explicit_chapter_field():
    raw = [{"character_name": "Lý Huyền", "chapter": 7, "stage_name": "rise"}]
    wps, health = _build_arc_waypoints(raw, {"Lý Huyền": "ly_huyen"})
    assert health.status == "ok"
    assert wps[0].chapter == 7
    assert wps[0].character_id == "ly_huyen"


def test_arc_waypoint_default_chapter_one_when_no_range_or_chapter():
    raw = [{"character_name": "X", "stage_name": "intro"}]
    wps, _ = _build_arc_waypoints(raw, {})
    assert wps[0].chapter == 1
    # No name in char_map — slugified
    assert wps[0].character_id == "x"


def test_arc_waypoint_partial_failure_keeps_valid():
    raw = [
        {"character_name": "Lý", "chapter_range": [3, 5], "stage_name": "ok"},
        {"character_name": "Bad", "chapter": "not-int", "stage_name": "x"},
    ]
    wps, health = _build_arc_waypoints(raw, {})
    assert health.status == "ok"
    assert health.item_count == 1
    assert health.last_error is not None


def test_arc_waypoint_all_rejected_marks_malformed():
    raw = [{"character_name": "X", "chapter": "not-int", "stage_name": "x"}]
    wps, health = _build_arc_waypoints(raw, {})
    assert health.status == "malformed"
    assert wps == []


# ---------------------------------------------------------------------------
# threads alternative input shapes
# ---------------------------------------------------------------------------

def test_threads_resolution_chapter_alias():
    raw = [{
        "thread_id": "t1",
        "description": "find sword",
        "planted_chapter": 1,
        "resolution_chapter": 9,
        "status": "open",
    }]
    threads, health = _build_threads(raw)
    assert health.status == "ok"
    assert threads[0].expected_close_chapter == 9


def test_threads_involved_characters_alias():
    raw = [{
        "thread_id": "t",
        "description": "x",
        "planted_chapter": 1,
        "involved_characters": ["A", "B"],
        "importance": "high",
    }]
    threads, _ = _build_threads(raw)
    assert threads[0].characters == ["A", "B"]
    assert threads[0].importance == "high"


def test_threads_unknown_status_defaults_to_open():
    raw = [{
        "thread_id": "t",
        "description": "x",
        "planted_chapter": 1,
        "status": "garbage_status",
    }]
    threads, _ = _build_threads(raw)
    assert threads[0].status == "open"


def test_threads_default_id_when_missing():
    raw = [{"description": "anon", "planted_chapter": 1}]
    threads, _ = _build_threads(raw)
    assert threads[0].id == "t1"


def test_threads_partial_failure_keeps_valid():
    raw = [
        {"thread_id": "t1", "description": "ok", "planted_chapter": 1},
        {"thread_id": "t2", "description": "bad", "planted_chapter": "not-int"},
    ]
    threads, health = _build_threads(raw)
    assert health.status == "ok"
    assert health.item_count == 1
    assert health.last_error is not None


def test_threads_all_rejected_marks_malformed():
    raw = [{"thread_id": "t", "description": "x", "planted_chapter": "not-int"}]
    threads, health = _build_threads(raw)
    assert health.status == "malformed"
    assert threads == []


# ---------------------------------------------------------------------------
# voice fingerprint optional-field projection
# ---------------------------------------------------------------------------

def test_voice_emotional_expression_dict_projected_to_string():
    raw = [{
        "name": "X",
        "verbal_tics": ["tic"],
        "dialogue_examples": ["ex"],
        "register": "formal",
        "emotional_baseline": "calm",
        "emotional_expression": {"angry": "shouts", "sad": "withdraws", "empty_value": None},
    }]
    fps, health = _build_voice_fingerprints(raw, {})
    assert health.status == "ok"
    assert "angry: shouts" in fps[0].emotional_expression
    assert "empty_value" not in fps[0].emotional_expression


def test_voice_emotional_expression_scalar_projected_to_string():
    raw = [{
        "name": "X",
        "register": "formal",
        "emotional_baseline": "calm",
        "emotional_expression": "stoic",
    }]
    fps, _ = _build_voice_fingerprints(raw, {})
    assert fps[0].emotional_expression == "stoic"


def test_voice_avg_sentence_length_unparseable_becomes_none():
    raw = [{
        "name": "X",
        "register": "formal",
        "emotional_baseline": "calm",
        "avg_sentence_length": "not a number",
    }]
    fps, _ = _build_voice_fingerprints(raw, {})
    assert fps[0].avg_sentence_length is None


def test_voice_uses_vocabulary_level_when_register_missing():
    raw = [{
        "name": "X",
        "vocabulary_level": "poetic",  # used as fallback for `register`
        "emotional_baseline": "calm",
    }]
    fps, health = _build_voice_fingerprints(raw, {})
    assert health.status == "ok"
    # register_ uses the alias "register" — verify projection path
    assert fps[0].register_ == "poetic"


def test_voice_emotional_state_alias_for_baseline():
    raw = [{
        "name": "X",
        "register": "formal",
        "emotional_state": "wary",  # legacy alias for emotional_baseline
    }]
    fps, health = _build_voice_fingerprints(raw, {})
    assert health.status == "ok"
    assert fps[0].emotional_baseline == "wary"


def test_voice_partial_failure_keeps_valid():
    raw = [
        {"name": "Good", "register": "formal", "emotional_baseline": "calm"},
        {"name": "Bad"},  # missing both register/vocab AND baseline
    ]
    fps, health = _build_voice_fingerprints(raw, {})
    assert health.status == "ok"
    assert health.item_count == 1
    assert health.last_error is not None


def test_voice_skips_non_dict_entries():
    raw = [
        {"name": "Good", "register": "formal", "emotional_baseline": "calm"},
        42,  # garbage entry, no model_dump → skipped (entry becomes None)
        None,
    ]
    fps, health = _build_voice_fingerprints(raw, {})
    assert health.item_count == 1
    assert fps[0].name == "Good"


def test_voice_uses_character_id_from_canonical():
    raw = [{
        "character_id": "explicit_id",
        "register": "formal",
        "emotional_baseline": "calm",
    }]
    fps, _ = _build_voice_fingerprints(raw, {})
    assert fps[0].character_id == "explicit_id"


def test_voice_unknown_character_id_when_no_name_or_map():
    raw = [{
        "register": "formal",
        "emotional_baseline": "calm",
    }]
    fps, _ = _build_voice_fingerprints(raw, {})
    assert fps[0].character_id == "unknown"


# ---------------------------------------------------------------------------
# build_l1_handoff full-circuit edge cases
# ---------------------------------------------------------------------------

def test_build_handoff_num_chapters_falls_back_to_chapters_when_no_outlines():
    draft = SimpleNamespace(
        characters=[],
        outlines=[],
        chapters=[SimpleNamespace(chapter_number=i) for i in range(1, 6)],
        conflict_web=[],
        foreshadowing_plan=[],
        arc_waypoints=[],
        open_threads=[],
        voice_fingerprints=[],
        voice_profiles=[],
    )
    env = build_l1_handoff(draft, story_id="x")
    assert env.num_chapters == 5


def test_build_handoff_anonymous_character_skipped_in_map():
    """Character with empty name should not appear in name→id map."""
    draft = SimpleNamespace(
        characters=[SimpleNamespace(name="", character_id="ghost")],
        outlines=[],
        chapters=[],
        conflict_web=[],
        foreshadowing_plan=[],
        arc_waypoints=[{"character_name": "Real", "chapter": 1, "stage_name": "x"}],
        open_threads=[],
        voice_fingerprints=[],
        voice_profiles=[],
    )
    env = build_l1_handoff(draft, story_id="x")
    # Real is not in map (only "" was passed and was skipped) → slugified
    assert env.arc_waypoints[0].character_id == "real"


def test_build_handoff_voice_fallback_to_voice_profiles_when_fingerprints_none():
    draft = SimpleNamespace(
        characters=[],
        outlines=[],
        chapters=[],
        conflict_web=[],
        foreshadowing_plan=[],
        arc_waypoints=[],
        open_threads=[],
        voice_fingerprints=None,
        voice_profiles=[
            {"name": "X", "register": "formal", "emotional_baseline": "calm"}
        ],
    )
    env = build_l1_handoff(draft, story_id="x")
    assert env.signal_health["voice_fingerprints"].status == "ok"
    assert env.voice_fingerprints[0].name == "X"


def test_signal_builders_keep_only_first_error_when_multiple_entries_fail():
    """Cover ``if first_error is None`` False branch — second-failure path keeps first."""
    # conflict_web — two malformed entries, both rejected
    web, health = _build_conflict_web([
        {"conflict_id": "c1", "characters": object(), "conflict_type": "p", "intensity": 1},
        {"conflict_id": "c2", "characters": object(), "conflict_type": "p", "intensity": 1},
    ])
    assert health.status == "malformed"
    assert health.last_error is not None

    # foreshadowing — two missing plant_chapter
    seeds, fhealth = _build_foreshadowing([
        {"id": "a", "payoff_chapter": 5, "description": "x"},
        {"id": "b", "payoff_chapter": 6, "description": "y"},
    ])
    assert fhealth.status == "malformed"

    # arc_waypoints — two unparseable
    wps, ahealth = _build_arc_waypoints(
        [{"chapter": "x"}, {"chapter": "y"}], {}
    )
    assert ahealth.status == "malformed"

    # threads — two unparseable
    threads, thealth = _build_threads(
        [{"description": "a", "planted_chapter": "x"}, {"description": "b", "planted_chapter": "y"}]
    )
    assert thealth.status == "malformed"

    # voice — two missing register+vocab+baseline
    fps, vhealth = _build_voice_fingerprints([{"name": "a"}, {"name": "b"}], {})
    assert vhealth.status == "malformed"


def test_build_handoff_returns_typed_envelope_even_with_all_signals_failing():
    """All-extraction-failed path still produces a valid (frozen) L1Handoff."""
    draft = SimpleNamespace(
        characters=[],
        outlines=[],
        chapters=[],
        conflict_web=None,
        foreshadowing_plan=None,
        arc_waypoints=None,
        open_threads=None,
        voice_fingerprints=None,
        voice_profiles=None,
    )
    env = build_l1_handoff(draft, story_id="ruined")
    assert isinstance(env, L1Handoff)
    for sig in ("conflict_web", "foreshadowing_plan", "arc_waypoints", "threads", "voice_fingerprints"):
        assert env.signal_health[sig].status == "extraction_failed"
    ok, blockers = env.is_usable_by_l2()
    assert ok is False
    assert set(blockers) == {
        "conflict_web", "foreshadowing_plan", "arc_waypoints", "threads", "voice_fingerprints",
    }
