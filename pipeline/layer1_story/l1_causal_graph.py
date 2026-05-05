"""L1 causal chain graph — tracks cause-effect relationships across chapters."""

import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from services.llm_client import LLMClient

logger = logging.getLogger(__name__)


class CausalEvent(BaseModel):
    event_id: str  # "{chapter}-{index}", e.g. "03-2"
    chapter: int
    description: str  # "Elena discovers the locked room"
    characters: list[str] = Field(default_factory=list)
    event_type: str = "setup"  # "reveal", "decision", "consequence", "setup"
    resolved: bool = False
    resolved_chapter: int = -1


class CausalGraph(BaseModel):
    events: list[CausalEvent] = Field(default_factory=list)

    def add_event(self, event: CausalEvent) -> None:
        """Append a causal event, skipping duplicates by event_id."""
        existing_ids = {e.event_id for e in self.events}
        if event.event_id not in existing_ids:
            self.events.append(event)

    def get_dependencies(self, chapter: int) -> list[CausalEvent]:
        """Return all unresolved events from chapters before *chapter*."""
        return [e for e in self.events if e.chapter < chapter and not e.resolved]

    def query_required_references(
        self, current_chapter: int, min_age: int = 2
    ) -> list[CausalEvent]:
        """Return unresolved events old enough to require acknowledgement.

        An event is 'old enough' when (current_chapter - event.chapter) >= min_age.
        """
        return [
            e for e in self.events
            if not e.resolved and (current_chapter - e.chapter) >= min_age
        ]

    def mark_resolved(self, event_id: str, resolved_chapter: int) -> None:
        """Mark an event as resolved in-place."""
        for e in self.events:
            if e.event_id == event_id:
                e.resolved = True
                e.resolved_chapter = resolved_chapter
                return
        logger.warning("mark_resolved: event_id '%s' not found", event_id)

    def to_dict(self) -> dict:
        """Serialise to plain dict for JSON persistence."""
        return {"events": [e.model_dump() for e in self.events]}

    @classmethod
    def from_dict(cls, data: dict) -> "CausalGraph":
        """Deserialise from plain dict."""
        events = []
        for raw in data.get("events", []):
            try:
                events.append(CausalEvent(**raw))
            except Exception as exc:
                logger.warning("Skipping malformed causal event: %s", exc)
        return cls(events=events)


# ---------------------------------------------------------------------------
# LLM extraction
# ---------------------------------------------------------------------------

_EXTRACT_PROMPT = (
    "Phân tích chương {chapter_num} và trích xuất TỐI ĐA 5 sự kiện nhân-quả quan trọng.\n"
    "Nhân vật chính: {characters}\n\n"
    "NỘI DUNG CHƯƠNG (500 ký tự đầu):\n{excerpt}\n\n"
    "Trả về JSON:\n"
    '{{"events": [{{'
    '"description": "mô tả ngắn sự kiện", '
    '"characters": ["tên"], '
    '"event_type": "setup|reveal|decision|consequence"'
    "}}]}}\n"
    "CHỈ trả JSON."
)


def extract_causal_events(
    llm: "LLMClient",
    chapter_text: str,
    chapter_num: int,
    characters: list | None = None,
) -> list[CausalEvent]:
    """Extract up to 5 causal events from chapter. Single LLM call (cheap tier)."""
    chars_text = ", ".join(characters[:8]) if characters else "không xác định"
    excerpt = chapter_text[:500]

    try:
        result = llm.generate_json(
            system_prompt="Bạn là chuyên gia phân tích cốt truyện. Trả về JSON.",
            user_prompt=_EXTRACT_PROMPT.format(
                chapter_num=chapter_num,
                characters=chars_text,
                excerpt=excerpt,
            ),
            temperature=0.2,
            max_tokens=600,
            model_tier="cheap",
        )
        if not isinstance(result, dict):
            logger.warning("extract_causal_events ch%d: expected dict, got %s", chapter_num, type(result).__name__)
            return []
        raw_events = result.get("events", [])[:5]
    except Exception as exc:
        logger.debug("extract_causal_events failed for ch%d: %s", chapter_num, exc)
        return []

    causal_events: list[CausalEvent] = []
    for idx, raw in enumerate(raw_events):
        if not isinstance(raw, dict):
            continue
        try:
            causal_events.append(
                CausalEvent(
                    event_id=f"{chapter_num:02d}-{idx + 1}",
                    chapter=chapter_num,
                    description=raw.get("description", ""),
                    characters=raw.get("characters", []),
                    event_type=raw.get("event_type", "setup"),
                )
            )
        except Exception as exc:
            logger.debug("Skipping malformed causal event dict: %s", exc)

    return causal_events


# ---------------------------------------------------------------------------
# Keyword-based validation (no LLM)
# ---------------------------------------------------------------------------

def validate_causal_references(
    chapter_text: str,
    required_events: list[CausalEvent],
) -> list[str]:
    """Check if required events are referenced in chapter.

    Returns list of unacknowledged event descriptions (keyword matching, no LLM).
    A match requires ≥30 % of significant words (len > 3) present in the text.
    """
    if not required_events:
        return []

    content_lower = chapter_text.lower()
    unacknowledged: list[str] = []

    for event in required_events:
        words = [w.lower() for w in event.description.split() if len(w) > 3]
        if not words:
            continue
        match_ratio = sum(1 for w in words if w in content_lower) / len(words)
        if match_ratio < 0.3:
            unacknowledged.append(event.description)

    return unacknowledged


# ---------------------------------------------------------------------------
# Prompt formatting
# ---------------------------------------------------------------------------

def format_causal_dependencies_for_prompt(events: list[CausalEvent]) -> str:
    """Format events as MUST ACKNOWLEDGE block for prompt injection."""
    if not events:
        return ""

    lines = ["## SỰ KIỆN NHÂN-QUẢ BẮT BUỘC NHẮC LẠI:"]
    for e in events:
        chars = f" [{', '.join(e.characters)}]" if e.characters else ""
        age_marker = f"ch.{e.chapter}"
        lines.append(
            f"- [{e.event_id}] ({e.event_type}) {e.description}{chars} — từ {age_marker}"
        )
    lines.append(
        "Phải nhắc đến hoặc xử lý ÍT NHẤT 1 sự kiện trên; "
        "ưu tiên sự kiện chưa được giải quyết lâu nhất."
    )
    return "\n".join(lines)
