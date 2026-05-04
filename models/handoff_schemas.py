"""L1 → L2 handoff envelope schemas (Sprint 1, Phase 1).

Single source of truth for the typed signal envelope produced by Layer 1
and consumed by Layer 2. Validated at one chokepoint (`pipeline/handoff_gate.py`)
before the simulator runs. Persisted to `pipeline_runs.handoff_envelope` (JSON).

See `plans/260503-2317-l1-l2-handoff-envelope/schema.md` for the full spec
and `docs/adr/0001-l1-handoff-envelope.md` for design rationale.
"""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


SIGNALS_VERSION = "1.0.0"


class SignalHealth(BaseModel):
    """Per-signal extraction status — never silently None."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "empty", "malformed", "extraction_failed"]
    reason: Optional[str] = None
    item_count: int = 0
    last_error: Optional[str] = None


class ConflictNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    parties: list[str]
    type: str
    intensity: int = Field(ge=1, le=5)
    activation_chapter: Optional[int] = None
    resolution_chapter: Optional[int] = None


class ConflictWeb(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[ConflictNode] = Field(default_factory=list)
    edges: list[dict] = Field(default_factory=list)


class ForeshadowingSeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    plant_chapter: int
    payoff_chapter: int
    description: str
    keywords: list[str] = Field(default_factory=list)
    semantic_anchor: str
    planted: bool = False
    paid_off: bool = False


class ArcWaypoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character_id: str
    chapter: int
    state_label: str
    required_evidence: list[str] = Field(default_factory=list)


class ThreadEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    opened_chapter: int
    expected_close_chapter: Optional[int] = None
    status: Literal["open", "advancing", "resolved", "abandoned"] = "open"
    characters: list[str] = Field(default_factory=list)
    importance: Optional[str] = None


class VoiceFingerprint(BaseModel):
    """Canonical voice profile — replaces all legacy aliases.

    Field naming note: `register` was renamed to `register_` (with alias="register")
    to avoid shadowing Pydantic's BaseModel.register class method. The JSON key
    remains "register" so serialized envelopes are unchanged.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    character_id: str
    verbal_tics: list[str] = Field(default_factory=list)
    dialogue_examples: list[str] = Field(default_factory=list)
    # Aliased to avoid shadowing BaseModel.register — JSON key stays "register".
    register_: str = Field(alias="register")
    emotional_baseline: str
    avoid_phrases: list[str] = Field(default_factory=list)
    name: Optional[str] = None
    vocabulary_level: Optional[str] = None
    sentence_style: Optional[str] = None
    emotional_expression: Optional[str] = None
    avg_sentence_length: Optional[float] = None


class L1Handoff(BaseModel):
    """Single source of truth from L1 → L2.

    Validated at `pipeline/handoff_gate.py` before the simulator runs.
    Persisted to `pipeline_runs.handoff_envelope` (JSON column).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    signals_version: str = SIGNALS_VERSION
    story_id: str
    num_chapters: int

    conflict_web: ConflictWeb = Field(default_factory=ConflictWeb)
    foreshadowing_plan: list[ForeshadowingSeed] = Field(default_factory=list)
    arc_waypoints: list[ArcWaypoint] = Field(default_factory=list)
    threads: list[ThreadEntry] = Field(default_factory=list)
    voice_fingerprints: list[VoiceFingerprint] = Field(default_factory=list)

    signal_health: dict[str, SignalHealth]

    def is_usable_by_l2(self) -> tuple[bool, list[str]]:
        """Returns (ok, blockers). L2 simulator should not run if ok==False."""
        blockers = [
            name
            for name, h in self.signal_health.items()
            if h.status in ("malformed", "extraction_failed")
        ]
        return (len(blockers) == 0, blockers)


class NegotiatedChapterContract(BaseModel):
    """Single rubric replacing both `ChapterContract` (L1) and `DramaContract` (L2).

    L1 fills threads/seeds/payoffs/waypoints/pacing; the simulator pass fills
    drama_target/escalation_events/causal_refs; the handoff gate sets
    reconciled + reconciliation_warnings.
    """

    model_config = ConfigDict(extra="forbid")

    chapter_num: int
    pacing_type: Literal["setup", "rising", "climax", "twist", "cooldown"]

    threads_advance: list[str] = Field(default_factory=list)
    seeds_plant: list[str] = Field(default_factory=list)
    payoffs_required: list[str] = Field(default_factory=list)
    arc_waypoints: list[str] = Field(default_factory=list)
    must_mention_characters: list[str] = Field(default_factory=list)

    # Preserved from legacy ChapterContract — used by verifier + prompt builder.
    character_arc_targets: dict[str, str] = Field(default_factory=dict)
    emotional_endpoint: str = ""
    previous_contract_failures: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    must_maintain: list[str] = Field(default_factory=list)
    world_rules: list[str] = Field(default_factory=list)
    secret_protection: dict[str, str] = Field(default_factory=dict)
    causal_dependencies: list[str] = Field(default_factory=list)

    drama_target: float = Field(default=0.0, ge=0.0, le=1.0)
    escalation_events: list[str] = Field(default_factory=list)
    causal_refs: list[str] = Field(default_factory=list)
    # Drama tolerance + subtext absorbed from legacy DramaContract for L2 validation.
    drama_tolerance: float = Field(default=0.15, ge=0.0, le=1.0)
    required_subtext: list[str] = Field(default_factory=list)
    forbidden_patterns: list[str] = Field(default_factory=list)

    reconciled: bool = False
    reconciliation_warnings: list[str] = Field(default_factory=list)
