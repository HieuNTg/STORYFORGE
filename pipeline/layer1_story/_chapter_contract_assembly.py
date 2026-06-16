"""Chapter-contract assembly + event-to-chapter matching helpers.

Internal module for ``chapter_contract_builder``: the pure-Python contract
builder and the strict event→chapter matchers. Re-exported by
``chapter_contract_builder`` so existing import paths and test patch targets
(``chapter_contract_builder.build_contract`` etc.) keep working. Kept separate
so the public module stays under the 200-line rule.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from models.schemas import (
        Character,
        ChapterOutline,
        ConflictEntry,
        ForeshadowingEntry,
        MacroArc,
        PlotThread,
    )

from models.narrative_schemas import ChapterContract

logger = logging.getLogger(__name__)

_CHAPTER_TAG_RE = re.compile(r"ch[_-]?(\d+)\b", re.IGNORECASE)


def extract_chapter_num(item: Any) -> Optional[int]:
    """Return the integer chapter for an event-like value, or None.

    Replaces the legacy `str(ch_num) in tag` substring match with strict integer
    extraction. Tries explicit `chapter` / `chapter_number` int fields first,
    then parses a `tag` / `suggested_insertion` string with `^ch[_-]?\\d+\\b`.

    Substring matching (e.g. `"3" in "chương 13"`) is intentionally never used.
    """
    if isinstance(item, dict):
        for key in ("chapter", "chapter_number"):
            if key in item:
                try:
                    return int(item[key])
                except (TypeError, ValueError):
                    pass
        for key in ("tag", "suggested_insertion"):
            tag = item.get(key)
            if isinstance(tag, str):
                m = _CHAPTER_TAG_RE.search(tag)
                if m:
                    return int(m.group(1))
    else:
        for key in ("chapter", "chapter_number"):
            val = getattr(item, key, None)
            if val is not None:
                try:
                    return int(val)
                except (TypeError, ValueError):
                    pass
        for key in ("tag", "suggested_insertion"):
            tag = getattr(item, key, None)
            if isinstance(tag, str):
                m = _CHAPTER_TAG_RE.search(tag)
                if m:
                    return int(m.group(1))
    return None


def events_for_chapter(events: list, ch_num: int) -> list:
    """Filter events whose extracted chapter number matches `ch_num` exactly."""
    return [e for e in (events or []) if extract_chapter_num(e) == ch_num]


def build_contract(
    chapter_num: int,
    outline: "ChapterOutline",
    threads: list["PlotThread"] | None = None,
    macro_arcs: list["MacroArc"] | None = None,
    conflicts: list["ConflictEntry"] | None = None,
    foreshadowing_plan: list["ForeshadowingEntry"] | None = None,
    characters: list["Character"] | None = None,
    previous_failures: list[str] | None = None,
    world_rules: list[str] | None = None,
    character_secrets: dict[str, str] | None = None,
) -> ChapterContract:
    """Build a ChapterContract from existing pipeline data. Pure Python."""
    threads = threads or []
    conflicts = conflicts or []
    foreshadowing_plan = foreshadowing_plan or []
    characters = characters or []

    # --- Threads to advance: open threads involving this chapter's characters ---
    chapter_chars = set(getattr(outline, "characters_involved", []) or [])
    open_threads = [t for t in threads if t.status != "resolved"]
    # Prioritize stale threads (not mentioned in 5+ chapters) and threads involving chapter characters
    must_advance = []
    for t in open_threads:
        staleness = chapter_num - (t.last_mentioned_chapter or t.planted_chapter)
        involves_chapter_char = bool(chapter_chars & set(t.involved_characters))
        if staleness >= 5 or involves_chapter_char:
            must_advance.append(t.thread_id)
    must_advance = must_advance[:5]  # cap to avoid prompt bloat

    # --- Foreshadowing seeds to plant / payoffs due ---
    must_plant = [
        f.hint
        for f in foreshadowing_plan
        if f.plant_chapter == chapter_num and not f.planted
    ]
    must_payoff = [
        f.hint
        for f in foreshadowing_plan
        if f.payoff_chapter == chapter_num and f.planted and not f.paid_off
    ]

    # --- Character arc targets ---
    arc_targets: dict[str, str] = {}
    try:
        from pipeline.layer1_story.arc_waypoint_generator import get_expected_stage

        for c in characters:
            wp = get_expected_stage(c, chapter_num)
            if wp:
                arc_targets[c.name] = f"{wp.stage_name} ({int(wp.progress_pct * 100)}%)"
    except Exception as e:
        logger.debug("Arc target resolution failed for ch%d: %s", chapter_num, e)

    # --- Pacing from outline ---
    pacing = getattr(outline, "pacing_type", "") or "rising"

    # --- Emotional endpoint from outline ---
    emotional = getattr(outline, "emotional_arc", "") or ""

    # --- Must-mention characters from outline ---
    must_mention = list(chapter_chars)

    # --- Proactive constraints ---
    secrets = character_secrets or {}
    forbidden_actions = [f"DO NOT reveal {secret}" for secret in secrets.values()]

    return ChapterContract(
        chapter_number=chapter_num,
        must_advance_threads=must_advance,
        must_plant_seeds=must_plant,
        must_payoff=must_payoff,
        character_arc_targets=arc_targets,
        pacing_type=pacing,
        emotional_endpoint=emotional,
        must_mention_characters=must_mention,
        previous_contract_failures=previous_failures or [],
        forbidden_actions=forbidden_actions,
        world_rules=world_rules or [],
        secret_protection=secrets,
    )
