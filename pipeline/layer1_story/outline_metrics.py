"""Objective, deterministic outline metrics (Sprint 2, P5).

Pure functions only — no LLM calls, no side effects, no randomness.
The embedding-based `beat_coverage_ratio` is the one part that calls
`EmbeddingService.embed_batch`; that call is deterministic given the same
model weights and is transparently cached by `EmbeddingCache`.

Formulas (all documented inline):
  conflict_web_density   = conflict edges / possible edges in character graph
  arc_trajectory_variance = normalised stddev of arc-waypoint counts per char
  pacing_distribution_skew = Shannon entropy / max_entropy  (1=uniform, 0=monotone)
  beat_coverage_ratio    = fraction of key_events covered by ≥1 chapter outline
                           (embedding cosine ≥ BEAT_COVERAGE_THRESHOLD)
  character_screen_time_gini = Gini coefficient of per-chapter mentions
  overall_score          = weighted sum per OUTLINE_METRIC_WEIGHTS (schema.md)

Individual floors for should_rewrite (see OutlineCritique in outline_critic.py):
  conflict_web_density   >= 0.10
  arc_trajectory_variance >= 0.10  (too-uniform arcs → skewed hero focus)
  pacing_distribution_skew >= 0.30
  beat_coverage_ratio    >= 0.50
  screen_time_balance    >= 0.30   (= 1 - gini)
"""

from __future__ import annotations

import logging
import math
import statistics
from typing import TYPE_CHECKING

from models.schemas import Character, ChapterOutline, ConflictEntry, ForeshadowingEntry
from models.semantic_schemas import OUTLINE_METRIC_WEIGHTS, OutlineMetrics
from services.embedding_service import get_embedding_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BEAT_COVERAGE_THRESHOLD: float = 0.50
"""Min cosine similarity for a key_event to count as 'covered' by a chapter."""

# Target pacing distribution (5 types, fractions must sum to 1.0).
# Derived from story-structure conventions; frozen for v1.
PACING_TARGET: dict[str, float] = {
    "setup": 0.10,
    "rising": 0.50,
    "climax": 0.15,
    "twist": 0.10,
    "cooldown": 0.15,
}

VALID_PACING_TYPES = frozenset(PACING_TARGET.keys())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _gini(values: list[float]) -> float:
    """Gini coefficient.  O(n log n).  Returns 0 for a single value.

    Formula: G = (2 * sum(i * x_i) / (n * sum(x_i))) - (n+1)/n
    where x_i are sorted ascending, i is 1-indexed.
    Equivalent to sum of all absolute differences / (2 * n^2 * mean).
    Both formulae give identical results; we use the sorting form as it avoids
    a double-nested loop.

    Range [0, 1].  0 = perfectly equal; 1 = all mass on one item.
    Returns 0.0 when sum(values) == 0 (no mentions at all).
    """
    n = len(values)
    if n == 0:
        return 0.0
    total = sum(values)
    if total == 0.0:
        return 0.0
    if n == 1:
        return 0.0
    xs = sorted(values)
    numerator = sum((2 * (i + 1) - n - 1) * x for i, x in enumerate(xs))
    return numerator / (n * total)


def _shannon_entropy(counts: dict[str, int]) -> float:
    """Shannon entropy (nats) of a count distribution.  Returns 0 for empty/uniform."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    result = 0.0
    for v in counts.values():
        if v > 0:
            p = v / total
            result -= p * math.log(p)
    return result


# ---------------------------------------------------------------------------
# Component metric functions — each returns (value: float, evidence: list[str])
# ---------------------------------------------------------------------------

def compute_conflict_web_density(
    conflict_web: list[ConflictEntry],
    characters: list[Character],
) -> tuple[float, list[str]]:
    """conflict_web_density = num_conflict_edges / max_possible_edges.

    max_possible_edges = n * (n-1) / 2  (undirected complete graph).
    Each ConflictEntry is one edge.  Multiple entries between the same pair are
    deduplicated — only the first is counted (spirit: density not frequency).
    Returns 0 if < 2 characters.
    """
    n = len(characters)
    if n < 2:
        return 0.0, ["< 2 characters: density undefined, returning 0"]

    # Count unique character-pair edges.  Order-insensitive.
    seen: set[frozenset[str]] = set()
    for entry in conflict_web:
        if len(entry.characters) >= 2:
            pair = frozenset(entry.characters[:2])
            seen.add(pair)

    max_edges = n * (n - 1) / 2
    density = min(1.0, len(seen) / max_edges)
    evidence = [
        f"{len(seen)} unique conflict edges across {n} characters (max={int(max_edges)})",
        f"density={density:.3f}",
    ]
    return density, evidence


def compute_arc_trajectory_variance(
    characters: list[Character],
) -> tuple[float, list[str]]:
    """arc_trajectory_variance = normalised stddev of arc_waypoint counts.

    stddev of counts normalised by dividing by max_count so result is [0, 1].
    Low value → arcs concentrated on one hero.
    High value → characters have varied arc richness (desired).
    Returns 0 if all characters have 0 waypoints.

    Normalisation: raw_stddev / max(1, max_count).
    Cap at 1.0 for safety.
    """
    counts = [len(c.arc_waypoints) for c in characters]
    if not counts or max(counts) == 0:
        return 0.0, ["no arc_waypoints on any character: variance=0"]

    if len(counts) == 1:
        return 0.0, [f"single character with {counts[0]} waypoints: variance=0"]

    raw_std = statistics.stdev(counts)
    max_count = max(counts)
    normalised = min(1.0, raw_std / max_count)

    evidence = [
        f"waypoint counts per char: {counts}",
        f"stdev={raw_std:.2f}, max={max_count}, normalised={normalised:.3f}",
    ]
    return normalised, evidence


def compute_pacing_distribution_skew(
    outlines: list[ChapterOutline],
) -> tuple[float, list[str]]:
    """pacing_distribution_skew = Shannon_entropy(observed) / ln(5).

    ln(5) is the max entropy for a 5-type uniform distribution (nats).
    1.0 = perfectly uniform; 0.0 = all chapters the same pacing type.

    Unknown pacing types are mapped to 'rising' with a warning (don't crash).

    L1-distance from target is also computed but not used for the returned
    score — it's included in evidence only for diagnostics.
    """
    n = len(outlines)
    if n == 0:
        return 0.0, ["empty outline list"]

    counts: dict[str, int] = {k: 0 for k in VALID_PACING_TYPES}
    unknown: list[str] = []
    for o in outlines:
        pt = (o.pacing_type or "rising").lower().strip()
        if pt in VALID_PACING_TYPES:
            counts[pt] += 1
        else:
            counts["rising"] += 1
            unknown.append(o.pacing_type)

    entropy = _shannon_entropy(counts)
    max_entropy = math.log(len(VALID_PACING_TYPES))  # ln(5) ≈ 1.609
    skew = entropy / max_entropy if max_entropy > 0 else 0.0
    skew = min(1.0, max(0.0, skew))

    # L1 distance vs target (evidence only)
    l1 = sum(abs(counts[k] / n - PACING_TARGET[k]) for k in VALID_PACING_TYPES)

    evidence = [
        f"pacing counts: { {k: v for k, v in counts.items() if v} }",
        f"entropy={entropy:.3f} / max={max_entropy:.3f} → skew={skew:.3f}",
        f"L1 vs target distribution: {l1:.3f}",
    ]
    if unknown:
        evidence.append(f"unknown pacing types mapped to 'rising': {unknown[:5]}")
    return skew, evidence


def compute_beat_coverage_ratio(
    outlines: list[ChapterOutline],
) -> tuple[float, list[str]]:
    """beat_coverage_ratio = fraction of key_events that appear in ≥1 chapter outline.

    Implementation:
    - Collects all key_events across ALL outlines (beat corpus).
    - For each unique beat, checks if any chapter outline's summary/key_events
      contains that beat via embedding cosine ≥ BEAT_COVERAGE_THRESHOLD.
    - Single embed_batch call per unique beat set.

    Fallback (embedding unavailable): exact-string-in-summary check.

    Returns (ratio, evidence).  ratio=1.0 when no beats exist (vacuous truth).
    """
    # Gather all key events as "beats"
    all_beats: list[str] = []
    for o in outlines:
        all_beats.extend(o.key_events)

    unique_beats = list(dict.fromkeys(all_beats))  # preserve order, deduplicate
    if not unique_beats:
        return 1.0, ["no key_events defined: coverage ratio=1.0 (vacuous)"]

    # Gather all chapter text targets (summary + key_events concatenated)
    chapter_texts = []
    for o in outlines:
        parts = [o.summary] + list(o.key_events)
        chapter_texts.append(" ".join(p for p in parts if p))

    # Try embedding-based coverage
    try:
        svc = get_embedding_service()
        if svc.is_available():
            return _beat_coverage_embedding(unique_beats, chapter_texts, svc)
    except Exception as exc:
        logger.warning("beat_coverage embedding failed, falling back to string match: %s", exc)

    # String-match fallback
    return _beat_coverage_string(unique_beats, chapter_texts)


def _beat_coverage_embedding(
    beats: list[str],
    chapter_texts: list[str],
    svc,
) -> tuple[float, list[str]]:
    """Embedding-based beat coverage.  Single batched call."""
    all_texts = beats + chapter_texts
    raw_bytes = svc.embed_batch(all_texts)

    import numpy as np
    from services.embedding_service import bytes_to_vec

    n_beats = len(beats)
    beat_vecs = [bytes_to_vec(b) for b in raw_bytes[:n_beats]]
    ch_vecs = [bytes_to_vec(b) for b in raw_bytes[n_beats:]]

    covered: list[str] = []
    uncovered: list[str] = []
    for beat, bvec in zip(beats, beat_vecs):
        max_sim = max(
            (float(np.dot(bvec, cv)) for cv in ch_vecs),
            default=0.0,
        )
        if max_sim >= BEAT_COVERAGE_THRESHOLD:
            covered.append(beat)
        else:
            uncovered.append(beat)

    ratio = len(covered) / len(beats)
    evidence = [
        f"{len(covered)}/{len(beats)} beats covered (threshold={BEAT_COVERAGE_THRESHOLD})",
        f"method=embedding",
    ]
    if uncovered:
        evidence.append(
            f"uncovered beats: {[b[:60] for b in uncovered[:5]]}"
        )
    return ratio, evidence


def _beat_coverage_string(
    beats: list[str],
    chapter_texts: list[str],
) -> tuple[float, list[str]]:
    """String-containment fallback for beat coverage."""
    all_text = " ".join(chapter_texts).lower()
    covered = [b for b in beats if b.lower() in all_text]
    uncovered = [b for b in beats if b.lower() not in all_text]
    ratio = len(covered) / len(beats)
    evidence = [
        f"{len(covered)}/{len(beats)} beats covered (method=string_fallback)",
    ]
    if uncovered:
        evidence.append(f"uncovered beats: {[b[:60] for b in uncovered[:5]]}")
    return ratio, evidence


def compute_character_screen_time_gini(
    outlines: list[ChapterOutline],
    characters: list[Character],
) -> tuple[float, list[str]]:
    """character_screen_time_gini = Gini(chapter_appearances_per_character).

    Counts how many chapters each character appears in (from characters_involved).
    Lower Gini = more balanced cast.
    """
    if not characters:
        return 0.0, ["no characters"]

    char_names = {c.name.lower() for c in characters}
    # Map display name → count
    counts: dict[str, int] = {c.name: 0 for c in characters}
    for o in outlines:
        seen_this_chapter: set[str] = set()
        for name in o.characters_involved:
            nl = name.lower()
            # Match against canonical names (case-insensitive)
            for char in characters:
                if char.name.lower() == nl and char.name not in seen_this_chapter:
                    counts[char.name] += 1
                    seen_this_chapter.add(char.name)
                    break

    values = list(counts.values())
    gini = _gini([float(v) for v in values])
    gini = min(1.0, max(0.0, gini))

    evidence = [
        f"chapter appearances: { {n: v for n, v in counts.items() if v > 0} }",
        f"gini={gini:.3f}",
    ]
    return gini, evidence


# ---------------------------------------------------------------------------
# Public composite function
# ---------------------------------------------------------------------------

def compute_outline_metrics(
    outlines: list[ChapterOutline],
    conflict_web: list[ConflictEntry],
    characters: list[Character],
    foreshadowing_plan: list[ForeshadowingEntry] | None = None,
) -> OutlineMetrics:
    """Compute all objective outline metrics. Pure and deterministic.

    Args:
        outlines: Chapter outlines from the L1 outline builder.
        conflict_web: ConflictEntry list from conflict_web_builder.
        characters: Character list from character_generator.
        foreshadowing_plan: Optional; used for num_seeds diagnostic counter.

    Returns:
        OutlineMetrics (frozen Pydantic model).
    """
    fp = foreshadowing_plan or []
    n_chapters = len(outlines)
    n_chars = len(characters)

    density, _d_ev = compute_conflict_web_density(conflict_web, characters)
    arc_var, _a_ev = compute_arc_trajectory_variance(characters)
    pacing_skew, _p_ev = compute_pacing_distribution_skew(outlines)
    beat_cov, _b_ev = compute_beat_coverage_ratio(outlines)
    gini, _g_ev = compute_character_screen_time_gini(outlines, characters)

    screen_time_balance = 1.0 - gini  # higher = more balanced

    # Weighted sum (weights from schema.md)
    overall = (
        OUTLINE_METRIC_WEIGHTS["conflict_web_density"] * density
        + OUTLINE_METRIC_WEIGHTS["arc_trajectory_variance"] * arc_var
        + OUTLINE_METRIC_WEIGHTS["pacing_distribution_skew"] * pacing_skew
        + OUTLINE_METRIC_WEIGHTS["beat_coverage_ratio"] * beat_cov
        + OUTLINE_METRIC_WEIGHTS["character_screen_time_balance"] * screen_time_balance
    )
    overall = min(1.0, max(0.0, overall))

    # Diagnostic counters
    num_arc_waypoints = sum(len(c.arc_waypoints) for c in characters)
    num_conflict_nodes = len(
        {name for entry in conflict_web for name in entry.characters}
    )

    # Floors for diagnostics log (mirrors outline_critic.METRIC_FLOORS)
    _floors = {
        "conflict_web_density": 0.10,
        "arc_trajectory_variance": 0.10,
        "pacing_distribution_skew": 0.30,
        "beat_coverage_ratio": 0.50,
        "character_screen_time_balance": 0.30,
    }
    _vals = {
        "conflict_web_density": density,
        "arc_trajectory_variance": arc_var,
        "pacing_distribution_skew": pacing_skew,
        "beat_coverage_ratio": beat_cov,
        "character_screen_time_balance": screen_time_balance,
    }
    floors_violated = [k for k, floor in _floors.items() if _vals[k] < floor]
    logger.info(
        "outline_metrics_built composite=%.2f floors_violated=%s",
        overall, floors_violated,
    )

    return OutlineMetrics(
        conflict_web_density=round(density, 6),
        arc_trajectory_variance=round(arc_var, 6),
        pacing_distribution_skew=round(pacing_skew, 6),
        beat_coverage_ratio=round(beat_cov, 6),
        character_screen_time_gini=round(gini, 6),
        overall_score=round(overall, 6),
        num_chapters=n_chapters,
        num_characters=n_chars,
        num_conflict_nodes=num_conflict_nodes,
        num_seeds=len(fp),
        num_arc_waypoints=num_arc_waypoints,
    )


__all__ = [
    "BEAT_COVERAGE_THRESHOLD",
    "PACING_TARGET",
    "compute_outline_metrics",
    "compute_conflict_web_density",
    "compute_arc_trajectory_variance",
    "compute_pacing_distribution_skew",
    "compute_beat_coverage_ratio",
    "compute_character_screen_time_gini",
]
