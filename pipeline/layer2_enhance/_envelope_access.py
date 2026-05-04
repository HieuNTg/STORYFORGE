"""Read-only accessors for the typed `L1Handoff` envelope (Sprint 1, Phase 4).

The handoff gate (`pipeline/orchestrator_layers.py`) stashes the validated
envelope on `draft._l1_handoff_envelope`. L2 consumers should read signals
through these helpers instead of touching `draft.<signal>` directly.

Behaviour: when an envelope is present, the helper returns its (frozen) value.
When absent (legacy paths, unit tests with bare drafts), the helper falls back
to the matching legacy attribute on `draft` so existing behaviour is preserved.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from models.handoff_schemas import ConflictWeb, L1Handoff


def get_envelope(draft) -> Optional["L1Handoff"]:
    """Return the typed envelope stashed by the handoff gate, or None.

    Defensive isinstance check: bare ``MagicMock`` drafts in unit tests
    expose auto-attrs for any name, including ``_l1_handoff_envelope``.
    Without this guard, every ``getattr`` call returned a truthy mock and
    the helpers below took the envelope branch with a garbage value
    instead of falling through to the legacy attribute.
    """
    from models.handoff_schemas import L1Handoff
    env = getattr(draft, "_l1_handoff_envelope", None)
    return env if isinstance(env, L1Handoff) else None


def conflict_web(draft) -> list:
    """Return conflict-web entries as a list (envelope nodes or legacy entries)."""
    env = get_envelope(draft)
    if env is not None:
        return list(env.conflict_web.nodes)
    return list(getattr(draft, "conflict_web", None) or [])


def foreshadowing_plan(draft) -> list:
    """Return foreshadowing seeds as a list."""
    env = get_envelope(draft)
    if env is not None:
        return list(env.foreshadowing_plan)
    return list(getattr(draft, "foreshadowing_plan", None) or [])


def arc_waypoints(draft) -> list:
    """Return arc waypoints as a list."""
    env = get_envelope(draft)
    if env is not None:
        return list(env.arc_waypoints)
    return list(getattr(draft, "arc_waypoints", None) or [])


def threads(draft) -> list:
    """Return open/resolved thread entries as a list."""
    env = get_envelope(draft)
    if env is not None:
        return list(env.threads)
    return list(getattr(draft, "open_threads", None) or []) + list(
        getattr(draft, "resolved_threads", None) or []
    )


def open_threads(draft) -> list:
    """Return only currently-open thread entries (status != resolved/abandoned)."""
    env = get_envelope(draft)
    if env is not None:
        return [t for t in env.threads if t.status in ("open", "advancing")]
    return list(getattr(draft, "open_threads", None) or [])


def resolved_threads(draft) -> list:
    """Return only resolved/abandoned thread entries."""
    env = get_envelope(draft)
    if env is not None:
        return [t for t in env.threads if t.status in ("resolved", "abandoned")]
    return list(getattr(draft, "resolved_threads", None) or [])


def voice_fingerprints(draft) -> list:
    """Return voice fingerprints as a list."""
    env = get_envelope(draft)
    if env is not None:
        return list(env.voice_fingerprints)
    return list(getattr(draft, "voice_fingerprints", None) or [])


def voice_profiles(draft) -> list:
    """Return voice profile dicts (envelope fingerprints projected to legacy dict shape).

    L2 voice consumers (`enhancer.build_voice_contracts`, `voice_fingerprint.build_from_draft`)
    expect dicts keyed by `name` with `vocabulary_level` / `sentence_style` /
    `emotional_expression` / `verbal_tics` / `dialogue_examples`. The envelope's
    `VoiceFingerprint` carries those fields after P5; we project to dicts here
    so callers stay shape-compatible without a parallel migration.
    """
    env = get_envelope(draft)
    if env is not None:
        out: list[dict] = []
        for vf in env.voice_fingerprints:
            out.append({
                "name": vf.name or vf.character_id,
                "character_id": vf.character_id,
                "vocabulary_level": vf.vocabulary_level or "",
                "sentence_style": vf.sentence_style or "",
                "emotional_expression": vf.emotional_expression or "",
                "verbal_tics": list(vf.verbal_tics),
                "dialogue_examples": list(vf.dialogue_examples),
                "register": vf.register_,
                "emotional_baseline": vf.emotional_baseline,
                "avoid_phrases": list(vf.avoid_phrases),
                "avg_sentence_length": vf.avg_sentence_length,
            })
        return out
    return list(getattr(draft, "voice_profiles", None) or [])
