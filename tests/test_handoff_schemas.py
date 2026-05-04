"""Unit tests for `models.handoff_schemas` (Sprint 1, Phase 1).

Covers schema construction, frozen behaviour, `is_usable_by_l2`, JSON
round-trip, and rejection of unknown/extra fields.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from models.handoff_schemas import (
    SIGNALS_VERSION,
    ArcWaypoint,
    ConflictNode,
    ConflictWeb,
    ForeshadowingSeed,
    L1Handoff,
    NegotiatedChapterContract,
    SignalHealth,
    ThreadEntry,
    VoiceFingerprint,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_health() -> dict[str, SignalHealth]:
    return {
        "conflict_web": SignalHealth(status="ok", item_count=2),
        "foreshadowing_plan": SignalHealth(status="ok", item_count=1),
        "arc_waypoints": SignalHealth(status="ok", item_count=1),
        "threads": SignalHealth(status="ok", item_count=1),
        "voice_fingerprints": SignalHealth(status="ok", item_count=1),
    }


def _full_envelope() -> L1Handoff:
    return L1Handoff(
        story_id="story_001",
        num_chapters=10,
        conflict_web=ConflictWeb(
            nodes=[
                ConflictNode(
                    id="c1",
                    parties=["Lý Huyền", "Hoàng Yến"],
                    type="ideological",
                    intensity=4,
                    activation_chapter=2,
                ),
                ConflictNode(
                    id="c2",
                    parties=["Lý Huyền", "Self"],
                    type="survival",
                    intensity=3,
                ),
            ],
            edges=[{"from": "c1", "to": "c2", "relation": "escalates"}],
        ),
        foreshadowing_plan=[
            ForeshadowingSeed(
                id="f1",
                plant_chapter=1,
                payoff_chapter=8,
                description="Ancient sword glows when betrayer is near",
                keywords=["sword", "glow"],
                semantic_anchor="kiếm cổ phát sáng",
            )
        ],
        arc_waypoints=[
            ArcWaypoint(
                character_id="ly_huyen",
                chapter=5,
                state_label="doubt → resolve",
                required_evidence=["faces mentor", "rejects easy path"],
            )
        ],
        threads=[
            ThreadEntry(
                id="t1",
                label="Tìm sự thật về gia tộc",
                opened_chapter=1,
                expected_close_chapter=10,
                status="advancing",
            )
        ],
        voice_fingerprints=[
            VoiceFingerprint(
                character_id="ly_huyen",
                verbal_tics=["Hừm.", "Ta hiểu rồi."],
                dialogue_examples=["Ta sẽ không lùi bước."],
                register="formal",
                emotional_baseline="kiên định",
                avoid_phrases=["LOL"],
            )
        ],
        signal_health=_clean_health(),
    )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

def test_signals_version_constant():
    assert SIGNALS_VERSION == "1.0.0"


def test_full_envelope_constructs():
    env = _full_envelope()
    assert env.signals_version == "1.0.0"
    assert env.story_id == "story_001"
    assert env.num_chapters == 10
    assert len(env.conflict_web.nodes) == 2
    assert env.foreshadowing_plan[0].id == "f1"
    assert env.arc_waypoints[0].character_id == "ly_huyen"
    assert env.threads[0].status == "advancing"
    assert env.voice_fingerprints[0].verbal_tics == ["Hừm.", "Ta hiểu rồi."]


def test_minimal_envelope_uses_defaults():
    env = L1Handoff(
        story_id="s",
        num_chapters=1,
        signal_health={"conflict_web": SignalHealth(status="empty")},
    )
    assert env.conflict_web.nodes == []
    assert env.foreshadowing_plan == []
    assert env.arc_waypoints == []
    assert env.threads == []
    assert env.voice_fingerprints == []


def test_conflict_node_intensity_bounds():
    with pytest.raises(ValidationError):
        ConflictNode(id="c", parties=["a"], type="power", intensity=0)
    with pytest.raises(ValidationError):
        ConflictNode(id="c", parties=["a"], type="power", intensity=6)


# ---------------------------------------------------------------------------
# SignalHealth
# ---------------------------------------------------------------------------

def test_signal_health_accepts_known_statuses():
    for status in ("ok", "empty", "malformed", "extraction_failed"):
        h = SignalHealth(status=status)
        assert h.status == status


def test_signal_health_rejects_unknown_status():
    with pytest.raises(ValidationError):
        SignalHealth(status="degraded")


def test_signal_health_rejects_extra_field():
    with pytest.raises(ValidationError):
        SignalHealth(status="ok", unknown_field=1)


# ---------------------------------------------------------------------------
# Frozen behaviour
# ---------------------------------------------------------------------------

def test_l1_handoff_is_frozen():
    env = _full_envelope()
    with pytest.raises(ValidationError):
        env.story_id = "other"


def test_l1_handoff_frozen_blocks_signal_health_replacement():
    env = _full_envelope()
    with pytest.raises(ValidationError):
        env.signal_health = {}


# ---------------------------------------------------------------------------
# is_usable_by_l2
# ---------------------------------------------------------------------------

def test_is_usable_by_l2_clean():
    env = _full_envelope()
    ok, blockers = env.is_usable_by_l2()
    assert ok is True
    assert blockers == []


def test_is_usable_by_l2_empty_is_still_usable():
    """`empty` is degraded-but-recoverable; only malformed/extraction_failed block."""
    health = _clean_health()
    health["arc_waypoints"] = SignalHealth(status="empty", reason="L1 produced no waypoints")
    env = _full_envelope().model_copy(update={"signal_health": health})
    ok, blockers = env.is_usable_by_l2()
    assert ok is True
    assert blockers == []


def test_is_usable_by_l2_malformed_blocks():
    health = _clean_health()
    health["conflict_web"] = SignalHealth(status="malformed", reason="missing parties")
    env = _full_envelope().model_copy(update={"signal_health": health})
    ok, blockers = env.is_usable_by_l2()
    assert ok is False
    assert blockers == ["conflict_web"]


def test_is_usable_by_l2_extraction_failed_blocks():
    health = _clean_health()
    health["voice_fingerprints"] = SignalHealth(
        status="extraction_failed",
        last_error="KeyError: 'register'",
    )
    env = _full_envelope().model_copy(update={"signal_health": health})
    ok, blockers = env.is_usable_by_l2()
    assert ok is False
    assert blockers == ["voice_fingerprints"]


def test_is_usable_by_l2_multiple_blockers():
    health = _clean_health()
    health["conflict_web"] = SignalHealth(status="malformed")
    health["threads"] = SignalHealth(status="extraction_failed")
    env = _full_envelope().model_copy(update={"signal_health": health})
    ok, blockers = env.is_usable_by_l2()
    assert ok is False
    assert set(blockers) == {"conflict_web", "threads"}


# ---------------------------------------------------------------------------
# Forbidden / extra fields
# ---------------------------------------------------------------------------

def test_l1_handoff_rejects_extra_fields():
    with pytest.raises(ValidationError):
        L1Handoff(
            story_id="s",
            num_chapters=1,
            signal_health={},
            mystery_field="nope",
        )


def test_voice_fingerprint_rejects_legacy_alias():
    """Canonical-only: legacy `speech_quirks` is forbidden, must be canonicalised upstream."""
    with pytest.raises(ValidationError):
        VoiceFingerprint(
            character_id="x",
            register="formal",
            emotional_baseline="calm",
            speech_quirks=["legacy"],
        )


# ---------------------------------------------------------------------------
# JSON round-trip
# ---------------------------------------------------------------------------

def test_json_round_trip_preserves_data():
    env = _full_envelope()
    raw = env.model_dump_json()
    reloaded = L1Handoff.model_validate_json(raw)
    assert reloaded == env
    assert reloaded.signals_version == env.signals_version
    assert reloaded.conflict_web.nodes[0].id == "c1"
    assert reloaded.signal_health["conflict_web"].status == "ok"


def test_json_round_trip_with_blockers():
    health = _clean_health()
    health["conflict_web"] = SignalHealth(
        status="malformed",
        reason="missing parties on node c1",
        item_count=0,
        last_error="ValidationError: parties",
    )
    env = _full_envelope().model_copy(update={"signal_health": health})
    reloaded = L1Handoff.model_validate_json(env.model_dump_json())
    ok, blockers = reloaded.is_usable_by_l2()
    assert ok is False
    assert blockers == ["conflict_web"]
    assert reloaded.signal_health["conflict_web"].last_error == "ValidationError: parties"


# ---------------------------------------------------------------------------
# NegotiatedChapterContract
# ---------------------------------------------------------------------------

def test_negotiated_contract_minimal():
    c = NegotiatedChapterContract(chapter_num=3, pacing_type="rising")
    assert c.drama_target == 0.0
    assert c.threads_advance == []
    assert c.reconciled is False
    assert c.reconciliation_warnings == []


def test_negotiated_contract_full():
    c = NegotiatedChapterContract(
        chapter_num=5,
        pacing_type="climax",
        threads_advance=["t1", "t2"],
        seeds_plant=["f1"],
        payoffs_required=["f0"],
        arc_waypoints=["w1"],
        must_mention_characters=["Lý Huyền"],
        drama_target=0.85,
        escalation_events=["betrayal", "reveal"],
        causal_refs=["e_3", "e_4"],
        reconciled=True,
        reconciliation_warnings=["clamped drama_target from 0.95"],
    )
    assert c.pacing_type == "climax"
    assert c.drama_target == 0.85
    assert c.reconciled is True
    assert "clamped" in c.reconciliation_warnings[0]


def test_negotiated_contract_drama_target_bounds():
    with pytest.raises(ValidationError):
        NegotiatedChapterContract(chapter_num=1, pacing_type="rising", drama_target=-0.1)
    with pytest.raises(ValidationError):
        NegotiatedChapterContract(chapter_num=1, pacing_type="rising", drama_target=1.1)


def test_negotiated_contract_pacing_type_enum():
    with pytest.raises(ValidationError):
        NegotiatedChapterContract(chapter_num=1, pacing_type="meandering")


def test_negotiated_contract_rejects_extra_fields():
    with pytest.raises(ValidationError):
        NegotiatedChapterContract(chapter_num=1, pacing_type="rising", legacy_drama_score=0.5)


def test_negotiated_contract_json_round_trip():
    c = NegotiatedChapterContract(
        chapter_num=7,
        pacing_type="cooldown",
        drama_target=0.4,
        reconciled=True,
        reconciliation_warnings=["pacing=cooldown clamped drama_target from 0.7 to 0.4"],
    )
    reloaded = NegotiatedChapterContract.model_validate_json(c.model_dump_json())
    assert reloaded == c


# ---------------------------------------------------------------------------
# Sprint 3 P1 — drama_ceiling field
# ---------------------------------------------------------------------------

def test_negotiated_contract_drama_ceiling_default_zero():
    c = NegotiatedChapterContract(chapter_num=1, pacing_type="rising")
    assert c.drama_ceiling == 0.0


def test_negotiated_contract_drama_ceiling_bounds():
    with pytest.raises(ValidationError):
        NegotiatedChapterContract(chapter_num=1, pacing_type="rising", drama_ceiling=-0.1)
    with pytest.raises(ValidationError):
        NegotiatedChapterContract(chapter_num=1, pacing_type="rising", drama_ceiling=1.1)


def test_negotiated_contract_legacy_dict_without_drama_ceiling_round_trips():
    """Sprint 1 envelopes persisted before the field existed must still validate."""
    legacy = {
        "chapter_num": 5,
        "pacing_type": "climax",
        "drama_target": 0.85,
        "drama_tolerance": 0.15,
        # no drama_ceiling key
    }
    c = NegotiatedChapterContract.model_validate(legacy)
    assert c.drama_ceiling == 0.0
    dumped = c.model_dump()
    assert dumped["drama_ceiling"] == 0.0


# ---------------------------------------------------------------------------
# Thread / Foreshadowing enum + bounds
# ---------------------------------------------------------------------------

def test_thread_status_enum():
    for s in ("open", "advancing", "resolved", "abandoned"):
        t = ThreadEntry(id="t", label="x", opened_chapter=1, status=s)
        assert t.status == s
    with pytest.raises(ValidationError):
        ThreadEntry(id="t", label="x", opened_chapter=1, status="dormant")


def test_foreshadowing_seed_defaults():
    f = ForeshadowingSeed(
        id="f",
        plant_chapter=1,
        payoff_chapter=5,
        description="d",
        semantic_anchor="anchor",
    )
    assert f.planted is False
    assert f.paid_off is False
    assert f.keywords == []
