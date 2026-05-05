"""Reader Simulator Agent — simulates reader experience to identify weak points.

Identifies:
- Boring/slow sections
- Confusing plot points
- Character behavior inconsistencies
- Pacing issues
- Engagement drops
"""

import logging
from typing import Optional
from pydantic import BaseModel, Field
from models.schemas import Chapter, EnhancedStory
from services.llm_client import LLMClient

logger = logging.getLogger(__name__)


class ReaderFeedback(BaseModel):
    """Feedback from simulated reader."""
    chapter_number: int
    engagement_score: float = Field(ge=0.0, le=1.0, description="0=bored, 1=engaged")
    confusion_points: list[str] = Field(default_factory=list)
    boring_sections: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


_READER_PROMPT = """Bạn là một độc giả đang đọc chương truyện. Đánh giá trải nghiệm đọc:

PHẠM VI: Bạn là editor critique craft (pacing, prose, dialogue rhythm, continuity, voice). KHÔNG được đề xuất thay đổi plot, character motivation, drama, hay conflict mới. Nếu thấy vấn đề plot, ghi chú trong `confusion_points` nhưng KHÔNG đưa vào `suggestions`.

Chương {chapter_number}: {title}
{content}

Trả về JSON:
{{
  "engagement_score": 0.0-1.0 (0=chán, 1=cuốn hút),
  "confusion_points": ["điểm gây khó hiểu..."],
  "boring_sections": ["đoạn nhàm chán..."],
  "highlights": ["điểm hay nhất..."],
  "suggestions": ["gợi ý cải thiện..."]
}}

Chỉ trả về JSON, không giải thích."""


class ReaderSimulator:
    """Simulates reader experience for quality feedback."""

    def __init__(self):
        self.llm = LLMClient()

    def simulate_reading(
        self,
        chapter: Chapter,
        context: str = "",
    ) -> ReaderFeedback:
        """Simulate a reader reading a chapter."""
        try:
            result = self.llm.generate_json(
                system_prompt="Bạn là độc giả truyện mạng. Đánh giá chương theo góc nhìn người đọc.",
                user_prompt=_READER_PROMPT.format(
                    chapter_number=chapter.chapter_number,
                    title=chapter.title or f"Chương {chapter.chapter_number}",
                    content=chapter.content[:8000],
                ),
                temperature=0.3,
                model_tier="cheap",
                max_tokens=500,
            )
            return ReaderFeedback(
                chapter_number=chapter.chapter_number,
                engagement_score=float(result.get("engagement_score", 0.5)),
                confusion_points=result.get("confusion_points", [])[:3],
                boring_sections=result.get("boring_sections", [])[:3],
                highlights=result.get("highlights", [])[:3],
                suggestions=result.get("suggestions", [])[:3],
            )
        except Exception as e:
            logger.warning(f"Reader simulation ch{chapter.chapter_number} failed: {e}")
            return ReaderFeedback(chapter_number=chapter.chapter_number, engagement_score=0.5)

    def simulate_story(
        self,
        enhanced: EnhancedStory,
        progress_callback=None,
    ) -> list[ReaderFeedback]:
        """Simulate reading entire story, return feedback per chapter."""
        feedbacks = []
        for chapter in enhanced.chapters:
            if progress_callback:
                progress_callback(f"[Reader] Simulating chapter {chapter.chapter_number}...")
            feedback = self.simulate_reading(chapter)
            feedbacks.append(feedback)
        return feedbacks

    def identify_weak_chapters(
        self,
        feedbacks: list[ReaderFeedback],
        engagement_threshold: float = 0.5,
    ) -> list[int]:
        """Return chapter numbers with low engagement."""
        return [
            fb.chapter_number
            for fb in feedbacks
            if fb.engagement_score < engagement_threshold
        ]


def run_reader_simulation(
    enhanced: EnhancedStory,
    enabled: bool = False,
    progress_callback=None,
) -> Optional[list[ReaderFeedback]]:
    """Run reader simulation if enabled."""
    if not enabled:
        return None
    try:
        simulator = ReaderSimulator()
        return simulator.simulate_story(enhanced, progress_callback)
    except Exception as e:
        logger.warning(f"Reader simulation failed: {e}")
        return None
