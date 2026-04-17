"""Timeline validator — ensures temporal consistency across chapters.

Feature #13: Detect timeline contradictions and impossible time sequences.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.llm_client import LLMClient

logger = logging.getLogger(__name__)

# Vietnamese time markers
TIME_PATTERNS = {
    "morning": re.compile(r'\b(sáng|bình minh|rạng đông)\b', re.IGNORECASE),
    "noon": re.compile(r'\b(trưa|giữa trưa)\b', re.IGNORECASE),
    "afternoon": re.compile(r'\b(chiều|xế chiều)\b', re.IGNORECASE),
    "evening": re.compile(r'\b(tối|hoàng hôn|chập tối)\b', re.IGNORECASE),
    "night": re.compile(r'\b(đêm|khuya|nửa đêm)\b', re.IGNORECASE),
}

RELATIVE_TIME = {
    "same_day": re.compile(r'\b(hôm nay|ngày hôm đó|cùng ngày)\b', re.IGNORECASE),
    "next_day": re.compile(r'\b(hôm sau|ngày hôm sau|sáng hôm sau)\b', re.IGNORECASE),
    "days_later": re.compile(r'\b(vài ngày sau|mấy ngày sau|nhiều ngày sau)\b', re.IGNORECASE),
    "week_later": re.compile(r'\b(tuần sau|một tuần sau)\b', re.IGNORECASE),
    "month_later": re.compile(r'\b(tháng sau|một tháng sau)\b', re.IGNORECASE),
    "flashback": re.compile(r'\b(nhớ lại|hồi tưởng|năm xưa|ngày xưa|trước đây)\b', re.IGNORECASE),
}

TIME_ORDER = ["morning", "noon", "afternoon", "evening", "night"]


@dataclass
class TimelineEvent:
    """A temporal event extracted from chapter."""
    chapter: int
    time_of_day: str = ""
    relative_marker: str = ""
    description: str = ""
    confidence: float = 0.5


@dataclass
class TimelineState:
    """Track timeline state across chapters."""
    events: list[TimelineEvent] = field(default_factory=list)
    current_day: int = 1
    last_time_of_day: str = ""

    def add_event(self, event: TimelineEvent) -> None:
        self.events.append(event)
        if event.time_of_day:
            self.last_time_of_day = event.time_of_day
        if event.relative_marker == "next_day":
            self.current_day += 1
        elif event.relative_marker == "days_later":
            self.current_day += 3
        elif event.relative_marker == "week_later":
            self.current_day += 7


def extract_time_markers(text: str) -> dict:
    """Extract time markers from text without LLM.

    Returns: {time_of_day: str, relative_markers: list}
    """
    time_of_day = ""
    for period, pattern in TIME_PATTERNS.items():
        if pattern.search(text):
            time_of_day = period
            break

    relative_markers = []
    for marker, pattern in RELATIVE_TIME.items():
        if pattern.search(text):
            relative_markers.append(marker)

    return {
        "time_of_day": time_of_day,
        "relative_markers": relative_markers,
    }


def detect_time_contradiction(
    prev_time: str,
    curr_time: str,
    relative_marker: str,
) -> str | None:
    """Check if time transition is logically valid.

    Returns contradiction description or None if valid.
    """
    if not prev_time or not curr_time:
        return None

    if relative_marker == "same_day":
        # Same day: time should progress forward
        prev_idx = TIME_ORDER.index(prev_time) if prev_time in TIME_ORDER else -1
        curr_idx = TIME_ORDER.index(curr_time) if curr_time in TIME_ORDER else -1

        if prev_idx >= 0 and curr_idx >= 0 and curr_idx < prev_idx:
            return f"Cùng ngày nhưng thời gian lùi: {prev_time} → {curr_time}"

    if relative_marker == "flashback":
        # Flashback is always valid
        return None

    return None


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
    if len(markers["relative_markers"]) > 1 or "flashback" in markers["relative_markers"]:
        try:
            result = llm.generate_json(
                system_prompt="Phân tích timeline. Trả JSON.",
                user_prompt=f"""Chương {chapter_number}:
{chapter_content[:2000]}

Thời gian chương trước: {timeline_state.last_time_of_day or 'không rõ'}
Ngày hiện tại: ngày {timeline_state.current_day}

Kiểm tra:
1. Có mâu thuẫn thời gian không?
2. Thời gian trong ngày?
3. Có flashback không?

{{"valid": true/false, "time_of_day": "morning/noon/afternoon/evening/night", "is_flashback": false, "contradiction": "mô tả nếu có"}}""",
                temperature=0.1,
                max_tokens=200,
                model_tier="cheap",
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
        relative_marker=markers["relative_markers"][0] if markers["relative_markers"] else "",
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
