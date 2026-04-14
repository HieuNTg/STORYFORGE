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
    """Per-chapter requirements contract — bundles ALL constraints into one structure.

    Generated from existing pipeline data (pure Python, no LLM).
    Injected into chapter write prompt so LLM knows exactly what to accomplish.
    Validated post-write to detect missed requirements.
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
