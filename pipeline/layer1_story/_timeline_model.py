"""Timeline model — time-marker patterns, events, and pure detection helpers.

Internal module: import these names via
``pipeline.layer1_story.timeline_validator``, which re-exports the full
public surface.
"""

import re
from dataclasses import dataclass, field

# Vietnamese time markers
TIME_PATTERNS = {
    "morning": re.compile(r"\b(sáng|bình minh|rạng đông)\b", re.IGNORECASE),
    "noon": re.compile(r"\b(trưa|giữa trưa)\b", re.IGNORECASE),
    "afternoon": re.compile(r"\b(chiều|xế chiều)\b", re.IGNORECASE),
    "evening": re.compile(r"\b(tối|hoàng hôn|chập tối)\b", re.IGNORECASE),
    "night": re.compile(r"\b(đêm|khuya|nửa đêm)\b", re.IGNORECASE),
}

RELATIVE_TIME = {
    "same_day": re.compile(r"\b(hôm nay|ngày hôm đó|cùng ngày)\b", re.IGNORECASE),
    "next_day": re.compile(r"\b(hôm sau|ngày hôm sau|sáng hôm sau)\b", re.IGNORECASE),
    "days_later": re.compile(
        r"\b(vài ngày sau|mấy ngày sau|nhiều ngày sau)\b", re.IGNORECASE
    ),
    "week_later": re.compile(r"\b(tuần sau|một tuần sau)\b", re.IGNORECASE),
    "month_later": re.compile(r"\b(tháng sau|một tháng sau)\b", re.IGNORECASE),
    "flashback": re.compile(
        r"\b(nhớ lại|hồi tưởng|năm xưa|ngày xưa|trước đây)\b", re.IGNORECASE
    ),
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
