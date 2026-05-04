"""L1 → L2 handoff envelope builder (Sprint 1, Phase 2).

Pulls existing draft fields into a typed `L1Handoff` envelope, recording per-signal
health (`ok` | `empty` | `malformed` | `extraction_failed`). Never raises on a
single bad signal — the validation gate (P3) decides what to do with degraded envelopes.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

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
from pipeline.layer1_story._legacy_voice_aliases import canonicalise_voice_profile

logger = logging.getLogger(__name__)


def _is_extraction_sentinel(value: Any) -> bool:
    """True when an upstream extractor stored an error sentinel instead of a real value."""
    return isinstance(value, dict) and "_error" in value


def _slug(value: str) -> str:
    return "_".join(value.lower().split())


def _build_conflict_web(raw: list) -> tuple[ConflictWeb, SignalHealth]:
    if raw is None:
        return ConflictWeb(), SignalHealth(status="extraction_failed", reason="conflict_web missing on draft")
    if _is_extraction_sentinel(raw):
        return ConflictWeb(), SignalHealth(
            status="extraction_failed",
            reason="upstream extractor reported error",
            last_error=str(raw.get("_error")),
        )
    if not isinstance(raw, list):
        return ConflictWeb(), SignalHealth(
            status="malformed",
            reason=f"conflict_web is {type(raw).__name__}, expected list",
        )
    if not raw:
        return ConflictWeb(), SignalHealth(status="empty", reason="no conflicts produced", item_count=0)

    nodes: list[ConflictNode] = []
    first_error: str | None = None
    for entry in raw:
        try:
            data = entry.model_dump() if hasattr(entry, "model_dump") else dict(entry)
            intensity = int(data.get("intensity", 1) or 1)
            intensity = max(1, min(5, intensity))
            nodes.append(
                ConflictNode(
                    id=str(data.get("conflict_id") or data.get("id") or f"c{len(nodes)+1}"),
                    parties=list(data.get("characters") or data.get("parties") or []),
                    type=str(data.get("conflict_type") or data.get("type") or "unknown"),
                    intensity=intensity,
                )
            )
        except (ValidationError, TypeError, ValueError) as exc:
            if first_error is None:
                first_error = str(exc).split("\n")[0]
            logger.debug("conflict_web entry rejected: %s", exc)

    if not nodes and first_error:
        return ConflictWeb(), SignalHealth(
            status="malformed",
            reason="all conflict entries rejected",
            last_error=first_error,
        )
    web = ConflictWeb(nodes=nodes)
    health = SignalHealth(status="ok", item_count=len(nodes))
    if first_error:
        health = SignalHealth(
            status="ok",
            item_count=len(nodes),
            reason="some entries dropped",
            last_error=first_error,
        )
    return web, health


def _build_foreshadowing(raw: list) -> tuple[list[ForeshadowingSeed], SignalHealth]:
    if raw is None:
        return [], SignalHealth(status="extraction_failed", reason="foreshadowing_plan missing on draft")
    if _is_extraction_sentinel(raw):
        return [], SignalHealth(
            status="extraction_failed",
            last_error=str(raw.get("_error")),
        )
    if not isinstance(raw, list):
        return [], SignalHealth(status="malformed", reason=f"expected list, got {type(raw).__name__}")
    if not raw:
        return [], SignalHealth(status="empty", item_count=0)

    seeds: list[ForeshadowingSeed] = []
    first_error: str | None = None
    for i, entry in enumerate(raw):
        try:
            data = entry.model_dump() if hasattr(entry, "model_dump") else dict(entry)
            seeds.append(
                ForeshadowingSeed(
                    id=str(data.get("id") or f"f{i+1}"),
                    plant_chapter=int(data["plant_chapter"]),
                    payoff_chapter=int(data["payoff_chapter"]),
                    description=str(data.get("description") or data.get("hint") or ""),
                    keywords=list(data.get("keywords") or []),
                    semantic_anchor=str(
                        data.get("semantic_anchor")
                        or data.get("hint")
                        or data.get("description")
                        or f"seed-{i+1}"
                    ),
                    planted=bool(data.get("planted", False)),
                    paid_off=bool(data.get("paid_off", False)),
                )
            )
        except (KeyError, ValidationError, TypeError, ValueError) as exc:
            if first_error is None:
                first_error = str(exc).split("\n")[0]
            logger.debug("foreshadowing entry rejected: %s", exc)

    if not seeds and first_error:
        return [], SignalHealth(status="malformed", reason="all entries rejected", last_error=first_error)
    health = SignalHealth(status="ok", item_count=len(seeds))
    if first_error:
        health = SignalHealth(status="ok", item_count=len(seeds), reason="some entries dropped", last_error=first_error)
    return seeds, health


def _build_arc_waypoints(
    raw: list,
    characters_by_name: dict[str, str],
) -> tuple[list[ArcWaypoint], SignalHealth]:
    if raw is None:
        return [], SignalHealth(status="extraction_failed", reason="arc_waypoints missing on draft")
    if _is_extraction_sentinel(raw):
        return [], SignalHealth(status="extraction_failed", last_error=str(raw.get("_error")))
    if not isinstance(raw, list):
        return [], SignalHealth(status="malformed", reason=f"expected list, got {type(raw).__name__}")
    if not raw:
        return [], SignalHealth(status="empty", item_count=0)

    waypoints: list[ArcWaypoint] = []
    first_error: str | None = None
    for entry in raw:
        try:
            data = entry if isinstance(entry, dict) else (
                entry.model_dump() if hasattr(entry, "model_dump") else dict(entry)
            )
            char_name = str(data.get("character_name") or data.get("character") or "")
            char_id = str(
                data.get("character_id")
                or characters_by_name.get(char_name, _slug(char_name) if char_name else "unknown")
            )
            ch_range = data.get("chapter_range") or []
            if "chapter" in data:
                chapter = int(data["chapter"])
            elif isinstance(ch_range, (list, tuple)) and ch_range:
                chapter = int(ch_range[0])
            else:
                chapter = 1
            waypoints.append(
                ArcWaypoint(
                    character_id=char_id,
                    chapter=chapter,
                    state_label=str(data.get("state_label") or data.get("stage_name") or ""),
                    required_evidence=list(data.get("required_evidence") or []),
                )
            )
        except (KeyError, ValidationError, TypeError, ValueError) as exc:
            if first_error is None:
                first_error = str(exc).split("\n")[0]
            logger.debug("arc_waypoint entry rejected: %s", exc)

    if not waypoints and first_error:
        return [], SignalHealth(status="malformed", reason="all entries rejected", last_error=first_error)
    health = SignalHealth(status="ok", item_count=len(waypoints))
    if first_error:
        health = SignalHealth(status="ok", item_count=len(waypoints), reason="some entries dropped", last_error=first_error)
    return waypoints, health


def _build_threads(raw: list) -> tuple[list[ThreadEntry], SignalHealth]:
    if raw is None:
        return [], SignalHealth(status="extraction_failed", reason="open_threads missing on draft")
    if _is_extraction_sentinel(raw):
        return [], SignalHealth(status="extraction_failed", last_error=str(raw.get("_error")))
    if not isinstance(raw, list):
        return [], SignalHealth(status="malformed", reason=f"expected list, got {type(raw).__name__}")
    if not raw:
        return [], SignalHealth(status="empty", item_count=0)

    _STATUS_MAP = {
        "open": "open",
        "progressing": "advancing",
        "advancing": "advancing",
        "resolved": "resolved",
        "abandoned": "abandoned",
    }

    threads: list[ThreadEntry] = []
    first_error: str | None = None
    for i, entry in enumerate(raw):
        try:
            data = entry.model_dump() if hasattr(entry, "model_dump") else dict(entry)
            raw_status = str(data.get("status") or "open").lower()
            status = _STATUS_MAP.get(raw_status, "open")
            expected_close = data.get("resolution_chapter") or data.get("expected_close_chapter")
            chars_raw = (
                data.get("characters")
                or data.get("involved_characters")
                or data.get("characters_involved")
                or []
            )
            importance = data.get("importance")
            threads.append(
                ThreadEntry(
                    id=str(data.get("thread_id") or data.get("id") or f"t{i+1}"),
                    label=str(data.get("description") or data.get("label") or ""),
                    opened_chapter=int(data.get("planted_chapter") or data.get("opened_chapter") or 1),
                    expected_close_chapter=int(expected_close) if expected_close else None,
                    status=status,
                    characters=[str(c) for c in chars_raw if c],
                    importance=str(importance) if importance else None,
                )
            )
        except (KeyError, ValidationError, TypeError, ValueError) as exc:
            if first_error is None:
                first_error = str(exc).split("\n")[0]
            logger.debug("thread entry rejected: %s", exc)

    if not threads and first_error:
        return [], SignalHealth(status="malformed", reason="all entries rejected", last_error=first_error)
    health = SignalHealth(status="ok", item_count=len(threads))
    if first_error:
        health = SignalHealth(status="ok", item_count=len(threads), reason="some entries dropped", last_error=first_error)
    return threads, health


def _build_voice_fingerprints(
    raw: list,
    characters_by_name: dict[str, str],
) -> tuple[list[VoiceFingerprint], SignalHealth]:
    if raw is None:
        return [], SignalHealth(status="extraction_failed", reason="voice_fingerprints missing on draft")
    if _is_extraction_sentinel(raw):
        return [], SignalHealth(status="extraction_failed", last_error=str(raw.get("_error")))
    if not isinstance(raw, list):
        return [], SignalHealth(status="malformed", reason=f"expected list, got {type(raw).__name__}")
    if not raw:
        return [], SignalHealth(status="empty", item_count=0)

    fingerprints: list[VoiceFingerprint] = []
    first_error: str | None = None
    for entry in raw:
        if not isinstance(entry, dict):
            entry = entry.model_dump() if hasattr(entry, "model_dump") else None
        if entry is None:
            continue
        canonical = canonicalise_voice_profile(entry)
        try:
            name = str(canonical.get("name") or canonical.get("character_id") or "")
            char_id = str(
                canonical.get("character_id")
                or characters_by_name.get(name, _slug(name) if name else "unknown")
            )
            ee_raw = canonical.get("emotional_expression")
            if isinstance(ee_raw, dict):
                ee_str = "; ".join(f"{k}: {v}" for k, v in ee_raw.items() if v) or None
            elif ee_raw:
                ee_str = str(ee_raw)
            else:
                ee_str = None
            avg_len_raw = canonical.get("avg_sentence_length")
            try:
                avg_len = float(avg_len_raw) if avg_len_raw is not None else None
            except (TypeError, ValueError):
                avg_len = None
            fingerprints.append(
                VoiceFingerprint(
                    character_id=char_id,
                    verbal_tics=list(canonical.get("verbal_tics") or []),
                    dialogue_examples=list(canonical.get("dialogue_examples") or []),
                    register=str(canonical["register"]) if "register" in canonical else (
                        canonical.get("vocabulary_level") or _raise_missing("register")
                    ),
                    emotional_baseline=str(
                        canonical.get("emotional_baseline")
                        or canonical.get("emotional_state")
                        or _raise_missing("emotional_baseline")
                    ),
                    avoid_phrases=list(canonical.get("avoid_phrases") or []),
                    name=name or None,
                    vocabulary_level=str(canonical["vocabulary_level"]) if canonical.get("vocabulary_level") else None,
                    sentence_style=str(canonical["sentence_style"]) if canonical.get("sentence_style") else None,
                    emotional_expression=ee_str,
                    avg_sentence_length=avg_len,
                )
            )
        except (KeyError, ValidationError, TypeError, ValueError) as exc:
            if first_error is None:
                first_error = str(exc).split("\n")[0]
            logger.debug("voice fingerprint rejected: %s", exc)

    if not fingerprints and first_error:
        return [], SignalHealth(status="malformed", reason="all entries rejected", last_error=first_error)
    health = SignalHealth(status="ok", item_count=len(fingerprints))
    if first_error:
        health = SignalHealth(status="ok", item_count=len(fingerprints), reason="some entries dropped", last_error=first_error)
    return fingerprints, health


def _raise_missing(field: str):
    raise KeyError(f"voice profile missing required field '{field}'")


def _characters_by_name(draft) -> dict[str, str]:
    """Build name → character_id map. Falls back to slugified name when no id present."""
    out: dict[str, str] = {}
    for c in getattr(draft, "characters", None) or []:
        name = getattr(c, "name", "") or ""
        if not name:
            continue
        cid = getattr(c, "character_id", "") or _slug(name)
        out[name] = cid
    return out


def _safe_extract(draft, attr: str):
    """Attribute access wrapped to record extraction failures into SignalHealth."""
    try:
        return getattr(draft, attr)
    except Exception as exc:  # pragma: no cover — defensive
        return {"_error": repr(exc)}


def build_l1_handoff(draft, story_id: str) -> L1Handoff:
    """Pull existing draft fields into a typed envelope.

    For each signal: extract → validate shape → emit SignalHealth.
    Never raises on missing/malformed signal — the validation gate (P3) decides.
    """
    char_map = _characters_by_name(draft)
    num_chapters = len(getattr(draft, "outlines", None) or []) or len(getattr(draft, "chapters", None) or [])

    raw_conflict = _safe_extract(draft, "conflict_web")
    conflict_web, conflict_health = _build_conflict_web(raw_conflict)

    raw_fore = _safe_extract(draft, "foreshadowing_plan")
    foreshadowing, fore_health = _build_foreshadowing(raw_fore)

    raw_waypoints = _safe_extract(draft, "arc_waypoints")
    arc_waypoints, waypoint_health = _build_arc_waypoints(raw_waypoints, char_map)

    raw_threads = _safe_extract(draft, "open_threads")
    threads, thread_health = _build_threads(raw_threads)

    raw_voice = _safe_extract(draft, "voice_fingerprints")
    if raw_voice is None or (isinstance(raw_voice, list) and not raw_voice):
        # Fall back to legacy `voice_profiles` if top-level fingerprints missing
        legacy = _safe_extract(draft, "voice_profiles")
        if isinstance(legacy, list) and legacy:
            raw_voice = legacy
    voice_fingerprints, voice_health = _build_voice_fingerprints(raw_voice, char_map)

    return L1Handoff(
        story_id=story_id,
        num_chapters=num_chapters,
        conflict_web=conflict_web,
        foreshadowing_plan=foreshadowing,
        arc_waypoints=arc_waypoints,
        threads=threads,
        voice_fingerprints=voice_fingerprints,
        signal_health={
            "conflict_web": conflict_health,
            "foreshadowing_plan": fore_health,
            "arc_waypoints": waypoint_health,
            "threads": thread_health,
            "voice_fingerprints": voice_health,
        },
    )
