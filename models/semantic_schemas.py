"""Semantic verification Pydantic schemas (Sprint 2).

Schemas for the local-embedding + NER-based verification pipeline that replaces
the LLM-based `verify_*_semantic` calls and substring/keyword heuristics in
foreshadowing, structural detection, and outline scoring.

See `plans/260504-1213-semantic-verification/schema.md` for the canonical spec.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


SEMANTIC_VERIFICATION_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Foreshadowing payoff verification
# ---------------------------------------------------------------------------


class SemanticPayoffMatch(BaseModel):
    """Single foreshadowing seed/payoff verification result.

    Emitted by `pipeline.semantic.foreshadowing_verifier` (P3) for each
    seed-or-payoff considered against a chapter. One match per (seed, chapter)
    pair regardless of role.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    seed_id: str
    """ForeshadowingSeed.id, or hint hash for legacy ForeshadowingEntry."""

    chapter_num: int
    role: Literal["seed", "payoff"]
    matched: bool
    confidence: float = Field(ge=0.0, le=1.0)
    """Max cosine similarity over chapter sentence spans."""

    threshold_used: float = Field(ge=0.0, le=1.0)
    matched_span: str | None = None
    """The chapter sentence span that produced the max similarity, truncated."""

    method: Literal["embedding", "keyword_fallback"] = "embedding"

    @property
    def status(self) -> Literal["matched", "missed", "weak"]:
        """Human-readable bucket for diagnostics. Not persisted."""
        if self.matched:
            return "matched"
        # "weak" = within 0.05 of threshold; otherwise "missed".
        if self.confidence >= max(0.0, self.threshold_used - 0.05):
            return "weak"
        return "missed"


# ---------------------------------------------------------------------------
# Structural findings (replaces dataclass StructuralIssue)
# ---------------------------------------------------------------------------


class StructuralFindingType(str, Enum):
    MISSING_KEY_EVENT = "missing_key_event"
    MISSING_CHARACTER = "missing_character"
    MISSED_ARC_WAYPOINT = "missed_arc_waypoint"
    PACING_VIOLATION = "pacing_violation"


class StructuralFinding(BaseModel):
    """Typed Pydantic finding emitted by ``pipeline.semantic.structural_detector``.

    Sprint 2 P4 introduced this to replace the legacy ``StructuralIssue``
    dataclass. Sprint 3 P7 completed the migration — the dataclass and its
    ``to_legacy_issue()`` adapter have been removed.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    finding_type: StructuralFindingType
    chapter_num: int
    severity: float = Field(ge=0.0, le=1.0)
    description: str
    fix_hint: str
    detection_method: Literal[
        "embedding", "ner", "ner_fallback_substring", "keyword"
    ]
    evidence: tuple[str, ...] = Field(default_factory=tuple)
    """Spans/entities supporting the finding. Tuple for hashability under frozen."""

    confidence: float = Field(ge=0.0, le=1.0)
    """Detector confidence — for missing-by-similarity this is `1 - max_sim`."""


# ---------------------------------------------------------------------------
# Outline objective metrics
# ---------------------------------------------------------------------------


# Frozen for v1. Bumping any weight requires a SEMANTIC_VERIFICATION_VERSION
# bump and ADR update. Documented in docs/adr/0002-semantic-verification.md.
OUTLINE_METRIC_WEIGHTS: dict[str, float] = {
    "conflict_web_density": 0.20,
    "arc_trajectory_variance": 0.20,
    "pacing_distribution_skew": 0.15,
    "beat_coverage_ratio": 0.30,
    "character_screen_time_balance": 0.15,  # 1 - gini
}
assert abs(sum(OUTLINE_METRIC_WEIGHTS.values()) - 1.0) < 1e-9, (
    "OUTLINE_METRIC_WEIGHTS must sum to 1.0"
)


class OutlineMetrics(BaseModel):
    """Deterministic objective metrics for an outline.

    All component scores in [0, 1]. `overall_score` is the weighted sum per
    `OUTLINE_METRIC_WEIGHTS`. Frozen for v1 — bumping weights = schema version
    bump.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SEMANTIC_VERIFICATION_VERSION

    # Component scores
    conflict_web_density: float = Field(ge=0.0, le=1.0)
    arc_trajectory_variance: float = Field(ge=0.0, le=1.0)
    pacing_distribution_skew: float = Field(ge=0.0, le=1.0)
    """1.0 = uniform pacing across chapters, 0.0 = monotone."""

    beat_coverage_ratio: float = Field(ge=0.0, le=1.0)
    character_screen_time_gini: float = Field(ge=0.0, le=1.0)
    """Lower = more balanced cast distribution."""

    overall_score: float = Field(ge=0.0, le=1.0)

    # Diagnostic counters (not part of score; for the API panel).
    num_chapters: int = Field(ge=0)
    num_characters: int = Field(ge=0)
    num_conflict_nodes: int = Field(ge=0)
    num_seeds: int = Field(ge=0)
    num_arc_waypoints: int = Field(ge=0)


# ---------------------------------------------------------------------------
# Per-chapter persisted aggregate
# ---------------------------------------------------------------------------


class ChapterSemanticFindings(BaseModel):
    """Persisted to `chapters.semantic_findings` (JSON column added in P2)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SEMANTIC_VERIFICATION_VERSION
    chapter_num: int
    payoff_matches: list[SemanticPayoffMatch] = Field(default_factory=list)
    structural_findings: list[StructuralFinding] = Field(default_factory=list)
    embedding_model: str
    """Model id that produced these findings — for cache-invalidation reads."""


__all__ = [
    "SEMANTIC_VERIFICATION_VERSION",
    "SemanticPayoffMatch",
    "StructuralFindingType",
    "StructuralFinding",
    "OUTLINE_METRIC_WEIGHTS",
    "OutlineMetrics",
    "ChapterSemanticFindings",
]
