"""Structured summary extractor — replaces simple 3-5 sentence summaries with rich data."""

import logging
from typing import TYPE_CHECKING

from models.schemas import StructuredSummary, PlotThread
from services import prompts

if TYPE_CHECKING:
    from services.llm_client import LLMClient

logger = logging.getLogger(__name__)


def extract_structured_summary(
    llm: "LLMClient",
    content: str,
    chapter_number: int,
    open_threads: list[PlotThread],
) -> tuple[StructuredSummary, str]:
    """Extract structured summary from chapter content.

    Returns (StructuredSummary, brief_text_summary) tuple.
    The brief text summary is for backward compat with context window.
    """
    threads_text = "\n".join(
        f"- [{t.thread_id}] {t.description}"
        for t in open_threads if t.status != "resolved"
    ) or "Chưa có threads."

    from services.text_utils import excerpt_text
    result = llm.generate_json(
        system_prompt="Trích xuất tóm tắt có cấu trúc. Trả về JSON bằng tiếng Việt.",
        user_prompt=prompts.EXTRACT_STRUCTURED_SUMMARY.format(
            chapter_number=chapter_number,
            content=excerpt_text(content, max_chars=4000),
            open_threads=threads_text,
        ),
        temperature=0.3,
        max_tokens=1500,
        model_tier="cheap",
    )

    structured = StructuredSummary(
        plot_critical_events=result.get("plot_critical_events", []),
        character_developments=result.get("character_developments", []),
        open_questions=result.get("open_questions", []),
        emotional_shift=result.get("emotional_shift", ""),
        threads_advanced=result.get("threads_advanced", []),
        threads_opened=result.get("threads_opened", []),
        threads_resolved=result.get("threads_resolved", []),
        chapter_ending_hook=result.get("chapter_ending_hook") or "",
        actual_emotional_arc=result.get("actual_emotional_arc") or "",
    )
    brief = result.get("brief_summary", "")
    return structured, brief
