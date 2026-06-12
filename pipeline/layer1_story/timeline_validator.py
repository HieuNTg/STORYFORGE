"""Timeline validator — ensures temporal consistency across chapters.

Feature #13: Detect timeline contradictions and impossible time sequences.
"""

import logging
from typing import TYPE_CHECKING

from pipeline.layer1_story._timeline_model import (
    RELATIVE_TIME,
    TIME_ORDER,
    TIME_PATTERNS,
    TimelineEvent,
    TimelineState,
    detect_time_contradiction,
    extract_time_markers,
)

if TYPE_CHECKING:
    from services.llm_client import LLMClient

__all__ = [
    "TIME_PATTERNS",
    "RELATIVE_TIME",
    "TIME_ORDER",
    "TimelineEvent",
    "TimelineState",
    "extract_time_markers",
    "detect_time_contradiction",
    "validate_chapter_timeline",
    "format_timeline_warning",
    "create_timeline_state",
]

logger = logging.getLogger(__name__)


def validate_chapter_timeline(
    llm: "LLMClient",
    chapter_content: str,
    chapter_number: int,
    timeline_state: TimelineState,
    model: str | None = None,
) -> dict:
    """Validate timeline consistency for a chapter.

    Returns: {
        'valid': bool,
        'contradictions': list[str],
        'extracted_time': dict,
        'warnings': list[str]
    }
    """
    # First pass: regex extraction (zero LLM cost)
    markers = extract_time_markers(chapter_content[:3000])

    contradictions = []
    warnings = []

    # Check for same-day time regression
    if markers["time_of_day"] and timeline_state.last_time_of_day:
        for rel in markers["relative_markers"]:
            contradiction = detect_time_contradiction(
                timeline_state.last_time_of_day,
                markers["time_of_day"],
                rel,
            )
            if contradiction:
                contradictions.append(contradiction)

    # LLM validation for complex cases
    if (
        len(markers["relative_markers"]) > 1
        or "flashback" in markers["relative_markers"]
    ):
        try:
            result = llm.generate_json(
                system_prompt="Phân tích timeline. Trả JSON.",
                user_prompt=f"""Chương {chapter_number}:
{chapter_content[:2000]}

Thời gian chương trước: {timeline_state.last_time_of_day or "không rõ"}
Ngày hiện tại: ngày {timeline_state.current_day}

Kiểm tra:
1. Có mâu thuẫn thời gian không?
2. Thời gian trong ngày?
3. Có flashback không?

{{"valid": true/false, "time_of_day": "morning/noon/afternoon/evening/night", "is_flashback": false, "contradiction": "mô tả nếu có"}}""",
                temperature=0.1,
                max_tokens=200,
                model_tier="cheap",
                expect="dict",
            )

            if not result.get("valid", True) and result.get("contradiction"):
                contradictions.append(result["contradiction"])

            if result.get("time_of_day"):
                markers["time_of_day"] = result["time_of_day"]

        except Exception as e:
            logger.debug(f"Timeline LLM check failed: {e}")

    # Update state
    event = TimelineEvent(
        chapter=chapter_number,
        time_of_day=markers["time_of_day"],
        relative_marker=markers["relative_markers"][0]
        if markers["relative_markers"]
        else "",
        confidence=0.8 if markers["time_of_day"] else 0.5,
    )
    timeline_state.add_event(event)

    # Warn about missing time markers
    if not markers["time_of_day"] and not markers["relative_markers"]:
        warnings.append(f"Chương {chapter_number}: không có marker thời gian rõ ràng")

    return {
        "valid": len(contradictions) == 0,
        "contradictions": contradictions,
        "extracted_time": markers,
        "warnings": warnings,
        "current_state": {
            "day": timeline_state.current_day,
            "time_of_day": timeline_state.last_time_of_day,
        },
    }


def format_timeline_warning(validation_result: dict) -> str:
    """Format timeline validation as warning text."""
    if validation_result.get("valid", True) and not validation_result.get("warnings"):
        return ""

    lines = []
    if validation_result.get("contradictions"):
        lines.append("## ⚠️ MÂU THUẪN TIMELINE:")
        for c in validation_result["contradictions"]:
            lines.append(f"- {c}")

    if validation_result.get("warnings"):
        if not lines:
            lines.append("## 📅 TIMELINE:")
        for w in validation_result["warnings"]:
            lines.append(f"- {w}")

    return "\n".join(lines)


def create_timeline_state() -> TimelineState:
    """Factory for timeline state tracking."""
    return TimelineState()
