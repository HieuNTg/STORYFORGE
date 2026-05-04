"""Narrative-specific schemas for Layer 1 story quality improvements.

Separated from schemas.py to keep file sizes manageable.
"""

from pydantic import BaseModel, Field


class ArcWaypoint(BaseModel):
    """Structured character arc stage — replaces flat arc_trajectory string.

    Each waypoint defines what stage a character should be at during a range
    of chapters, enabling predictive arc tracking instead of retroactive drift detection.
    """
    stage_name: str = Field(description="Tên giai đoạn: 'phủ nhận', 'thử thách', 'khủng hoảng', 'chuyển hóa'...")
    chapter_range: list[int] = Field(
        min_length=2, max_length=2,
        description="[chapter_start, chapter_end] for this stage",
    )
    description: str = Field(default="", description="Mô tả ngắn gọn giai đoạn này")
    emotional_state: str = Field(default="", description="Trạng thái cảm xúc chủ đạo")
    progress_pct: float = Field(default=0.0, ge=0.0, le=1.0, description="Tiến trình arc 0.0-1.0")


class ChapterContract(BaseModel):
    """Per-chapter requirements contract.

    Sprint 1 P5: backwards-compatible facade over `NegotiatedChapterContract`.
    Existing call sites still see the legacy field names (`chapter_number`,
    `must_advance_threads`, `must_plant_seeds`, `must_payoff`, `pacing_type`)
    while the unified model in `models/handoff_schemas.py` supplies the L2
    portion (drama_target, escalation_events, causal_refs) and reconciliation
    state. New code should construct `NegotiatedChapterContract` directly.
    """
    chapter_number: int
    must_advance_threads: list[str] = Field(default_factory=list, description="Thread IDs that MUST progress")
    must_plant_seeds: list[str] = Field(default_factory=list, description="Foreshadowing hints to plant")
    must_payoff: list[str] = Field(default_factory=list, description="Foreshadowing payoffs due")
    character_arc_targets: dict[str, str] = Field(default_factory=dict, description="{name: 'stage (pct%)'}")
    pacing_type: str = Field(default="rising", description="Expected pacing type")
    emotional_endpoint: str = Field(default="", description="Target emotional state at chapter end")
    must_mention_characters: list[str] = Field(default_factory=list, description="Characters that MUST appear")
    previous_contract_failures: list[str] = Field(default_factory=list, description="Missed items from previous chapter")
    forbidden_actions: list[str] = Field(default_factory=list, description="Actions that MUST NOT happen")
    must_maintain: list[str] = Field(default_factory=list, description="Facts/states that must remain true")
    world_rules: list[str] = Field(default_factory=list, description="World rules to enforce")
    secret_protection: dict[str, str] = Field(default_factory=dict, description="{char: secret} - secrets to guard")
    causal_dependencies: list[str] = Field(default_factory=list, description="Prior events that MUST be acknowledged")

    # L2 portion (filled post-simulator) — single rubric, no parallel DramaContract.
    drama_target: float = Field(default=0.0, ge=0.0, le=1.0)
    drama_tolerance: float = Field(default=0.15, ge=0.0, le=1.0)
    escalation_events: list[str] = Field(default_factory=list)
    required_subtext: list[str] = Field(default_factory=list)
    causal_refs: list[str] = Field(default_factory=list)
    forbidden_patterns: list[str] = Field(default_factory=list)
    reconciled: bool = False
    reconciliation_warnings: list[str] = Field(default_factory=list)

    def to_negotiated(self):
        """Return an equivalent `NegotiatedChapterContract`. Mapping preserves
        IDs as strings (legacy stored hint-text in `must_*`; we forward verbatim)."""
        from models.handoff_schemas import NegotiatedChapterContract
        pacing = self.pacing_type or "rising"
        if pacing not in ("setup", "rising", "climax", "twist", "cooldown"):
            pacing = "rising"
        return NegotiatedChapterContract(
            chapter_num=self.chapter_number,
            pacing_type=pacing,
            threads_advance=list(self.must_advance_threads),
            seeds_plant=list(self.must_plant_seeds),
            payoffs_required=list(self.must_payoff),
            arc_waypoints=[],
            must_mention_characters=list(self.must_mention_characters),
            character_arc_targets=dict(self.character_arc_targets),
            emotional_endpoint=self.emotional_endpoint,
            previous_contract_failures=list(self.previous_contract_failures),
            forbidden_actions=list(self.forbidden_actions),
            must_maintain=list(self.must_maintain),
            world_rules=list(self.world_rules),
            secret_protection=dict(self.secret_protection),
            causal_dependencies=list(self.causal_dependencies),
            drama_target=self.drama_target,
            drama_tolerance=self.drama_tolerance,
            escalation_events=list(self.escalation_events),
            required_subtext=list(self.required_subtext),
            causal_refs=list(self.causal_refs),
            forbidden_patterns=list(self.forbidden_patterns),
            reconciled=self.reconciled,
            reconciliation_warnings=list(self.reconciliation_warnings),
        )
