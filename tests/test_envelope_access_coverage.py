"""Coverage tests for `pipeline.layer2_enhance._envelope_access` accessors.

Verifies both branches of every helper:
  - Envelope present  → returns projection from `L1Handoff` fields.
  - Envelope absent   → falls back to legacy `draft.<attr>` shape.
  - Bare MagicMock    → defensive isinstance guard returns None envelope.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from models.handoff_schemas import (
    ArcWaypoint,
    ConflictNode,
    ConflictWeb,
    ForeshadowingSeed,
    L1Handoff,
    SignalHealth,
    ThreadEntry,
    VoiceFingerprint,
)
from pipeline.layer2_enhance import _envelope_access as ea


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ok_health() -> dict[str, SignalHealth]:
    sigs = ("conflict_web", "foreshadowing", "arcs", "threads", "voice")
    return {s: SignalHealth(status="ok", item_count=1) for s in sigs}


def _envelope() -> L1Handoff:
    return L1Handoff(
        story_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        signals_version="1.0.0",
        num_chapters=3,
        conflict_web=ConflictWeb(
            nodes=[ConflictNode(id="c1", parties=["A", "B"], type="ideological", intensity=4)],
            edges=[],
        ),
        foreshadowing_plan=[
            ForeshadowingSeed(
                id="f1", plant_chapter=1, payoff_chapter=3,
                description="d", semantic_anchor="s",
            )
        ],
        arc_waypoints=[
            ArcWaypoint(
                character_id="A", chapter=1,
                state_label="phủ nhận", required_evidence=["e1"],
            )
        ],
        threads=[
            ThreadEntry(id="t1", label="d", opened_chapter=1, status="open"),
            ThreadEntry(id="t2", label="d2", opened_chapter=2, status="resolved"),
            ThreadEntry(id="t3", label="d3", opened_chapter=2, status="advancing"),
            ThreadEntry(id="t4", label="d4", opened_chapter=3, status="abandoned"),
        ],
        voice_fingerprints=[
            VoiceFingerprint(
                name="A", character_id="a",
                vocabulary_level="formal", sentence_style="short",
                emotional_expression="reserved",
                verbal_tics=["Hừ."], dialogue_examples=["Ta hiểu."],
                register_="formal", emotional_baseline="kiên định",
                avoid_phrases=[], avg_sentence_length=12.0,
            )
        ],
        signal_health=_ok_health(),
    )


# ---------------------------------------------------------------------------
# Envelope-present branch
# ---------------------------------------------------------------------------


def test_get_envelope_returns_typed_value():
    draft = SimpleNamespace(_l1_handoff_envelope=_envelope())
    out = ea.get_envelope(draft)
    assert isinstance(out, L1Handoff)


def test_get_envelope_rejects_magicmock_truthy_attr():
    """MagicMock auto-creates any attribute; isinstance guard must filter."""
    draft = MagicMock()
    assert ea.get_envelope(draft) is None


def test_get_envelope_returns_none_when_attr_missing():
    draft = SimpleNamespace()
    assert ea.get_envelope(draft) is None


def test_get_envelope_returns_none_when_attr_is_garbage():
    draft = SimpleNamespace(_l1_handoff_envelope="not-an-envelope")
    assert ea.get_envelope(draft) is None


def test_conflict_web_with_envelope():
    draft = SimpleNamespace(_l1_handoff_envelope=_envelope())
    out = ea.conflict_web(draft)
    assert len(out) == 1
    assert out[0].id == "c1"


def test_foreshadowing_plan_with_envelope():
    draft = SimpleNamespace(_l1_handoff_envelope=_envelope())
    out = ea.foreshadowing_plan(draft)
    assert len(out) == 1
    assert out[0].id == "f1"


def test_arc_waypoints_with_envelope():
    draft = SimpleNamespace(_l1_handoff_envelope=_envelope())
    out = ea.arc_waypoints(draft)
    assert len(out) == 1
    assert out[0].character_id == "A"


def test_threads_with_envelope_returns_all():
    draft = SimpleNamespace(_l1_handoff_envelope=_envelope())
    out = ea.threads(draft)
    assert len(out) == 4


def test_open_threads_with_envelope_filters_to_open_and_advancing():
    draft = SimpleNamespace(_l1_handoff_envelope=_envelope())
    out = ea.open_threads(draft)
    statuses = {t.status for t in out}
    assert statuses == {"open", "advancing"}


def test_resolved_threads_with_envelope_filters_to_resolved_and_abandoned():
    draft = SimpleNamespace(_l1_handoff_envelope=_envelope())
    out = ea.resolved_threads(draft)
    statuses = {t.status for t in out}
    assert statuses == {"resolved", "abandoned"}


def test_voice_fingerprints_with_envelope():
    draft = SimpleNamespace(_l1_handoff_envelope=_envelope())
    out = ea.voice_fingerprints(draft)
    assert len(out) == 1
    assert out[0].name == "A"


def test_voice_profiles_with_envelope_projects_to_legacy_dicts():
    draft = SimpleNamespace(_l1_handoff_envelope=_envelope())
    out = ea.voice_profiles(draft)
    assert len(out) == 1
    p = out[0]
    assert p["name"] == "A"
    assert p["vocabulary_level"] == "formal"
    assert p["verbal_tics"] == ["Hừ."]
    assert p["register"] == "formal"
    assert p["avg_sentence_length"] == 12.0


def test_voice_profiles_falls_back_to_character_id_when_name_empty():
    env = _envelope()
    # Construct a vf with empty name; need to bypass frozen via reconstruction
    vf = VoiceFingerprint(
        name="", character_id="char_42",
        verbal_tics=[], dialogue_examples=[],
        register_="formal", emotional_baseline="neutral",
        avoid_phrases=[], avg_sentence_length=None,
    )
    env2 = env.model_copy(update={"voice_fingerprints": [vf]})
    draft = SimpleNamespace(_l1_handoff_envelope=env2)
    out = ea.voice_profiles(draft)
    assert out[0]["name"] == "char_42"


# ---------------------------------------------------------------------------
# Legacy fallback branch
# ---------------------------------------------------------------------------


def test_conflict_web_legacy_fallback():
    draft = SimpleNamespace(conflict_web=[{"id": "x"}])
    assert ea.conflict_web(draft) == [{"id": "x"}]


def test_conflict_web_legacy_fallback_none_returns_empty():
    draft = SimpleNamespace(conflict_web=None)
    assert ea.conflict_web(draft) == []


def test_foreshadowing_plan_legacy_fallback():
    draft = SimpleNamespace(foreshadowing_plan=[{"id": "f"}])
    assert ea.foreshadowing_plan(draft) == [{"id": "f"}]


def test_arc_waypoints_legacy_fallback():
    draft = SimpleNamespace(arc_waypoints=[{"name": "A"}])
    assert ea.arc_waypoints(draft) == [{"name": "A"}]


def test_threads_legacy_fallback_concatenates_open_and_resolved():
    draft = SimpleNamespace(
        open_threads=[{"id": "t1"}],
        resolved_threads=[{"id": "t2"}],
    )
    out = ea.threads(draft)
    assert len(out) == 2
    assert {t["id"] for t in out} == {"t1", "t2"}


def test_open_threads_legacy_fallback():
    draft = SimpleNamespace(open_threads=[{"id": "t1"}])
    assert ea.open_threads(draft) == [{"id": "t1"}]


def test_open_threads_legacy_fallback_missing_attr():
    draft = SimpleNamespace()
    assert ea.open_threads(draft) == []


def test_resolved_threads_legacy_fallback():
    draft = SimpleNamespace(resolved_threads=[{"id": "t2"}])
    assert ea.resolved_threads(draft) == [{"id": "t2"}]


def test_voice_fingerprints_legacy_fallback():
    draft = SimpleNamespace(voice_fingerprints=[{"name": "A"}])
    assert ea.voice_fingerprints(draft) == [{"name": "A"}]


def test_voice_profiles_legacy_fallback():
    draft = SimpleNamespace(voice_profiles=[{"name": "A"}])
    assert ea.voice_profiles(draft) == [{"name": "A"}]


def test_voice_profiles_legacy_fallback_missing_attr_returns_empty():
    draft = SimpleNamespace()
    assert ea.voice_profiles(draft) == []
