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
