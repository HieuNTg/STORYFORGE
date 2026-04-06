"""Conflict web builder — creates and tracks character conflicts."""

import logging
from typing import Optional, TYPE_CHECKING

from models.schemas import Character, ConflictEntry, MacroArc
from services import prompts

if TYPE_CHECKING:
    from services.llm_client import LLMClient

logger = logging.getLogger(__name__)


def generate_conflict_web(
    llm: "LLMClient",
    title: str,
    genre: str,
    characters: list[Character],
    macro_arcs: list[MacroArc],
    model: Optional[str] = None,
) -> list[ConflictEntry]:
    """Generate a network of conflicts between characters."""
    chars_text = "\n".join(
        f"- {c.name} ({c.role}): {c.personality}, Xung đột nội tâm: {c.internal_conflict}"
        for c in characters
    )
    from pipeline.layer1_story.macro_outline_builder import format_arcs_for_prompt
    arcs_text = format_arcs_for_prompt(macro_arcs)

    result = llm.generate_json(
        system_prompt="Bạn là chuyên gia xây dựng xung đột truyện. BẮT BUỘC viết bằng tiếng Việt. Trả về JSON.",
        user_prompt=prompts.GENERATE_CONFLICT_WEB.format(
            genre=genre, title=title,
            characters=chars_text, macro_arcs=arcs_text,
        ),
        temperature=0.85,
        model=model,
    )
    conflicts = []
    for c in result.get("conflicts", []):
        if isinstance(c, dict):
            try:
                conflicts.append(ConflictEntry(**c))
            except Exception as e:
                logger.warning("Skipping malformed conflict: %s", e)
    return conflicts


def get_active_conflicts(
    conflicts: list[ConflictEntry],
    current_arc: int,
) -> list[ConflictEntry]:
    """Get conflicts active in the current arc."""
    active = []
    for c in conflicts:
        if c.status == "resolved":
            continue
        if c.arc_range:
            try:
                parts = c.arc_range.split("-")
                start = int(parts[0])
                end = int(parts[-1])
                if start <= current_arc <= end:
                    active.append(c)
            except (ValueError, IndexError):
                active.append(c)
        else:
            active.append(c)
    return active


def format_conflicts_for_prompt(conflicts: list[ConflictEntry]) -> str:
    """Format active conflicts for chapter writing prompt."""
    if not conflicts:
        return "Không có xung đột active."
    lines = []
    for c in conflicts:
        chars = " vs ".join(c.characters) if c.conflict_type != "internal" else c.characters[0]
        lines.append(f"- [{c.conflict_type}] {chars}: {c.description} ({c.status})")
    return "\n".join(lines)


def update_conflict_status(
    conflicts: list[ConflictEntry],
    chapter_content: str,
    chapter_number: int,
) -> list[ConflictEntry]:
    """Simple heuristic update: if trigger_event keywords appear in content, activate conflict."""
    content_lower = chapter_content.lower()
    for c in conflicts:
        if c.status == "dormant" and c.trigger_event:
            # Simple keyword match — trigger_event words found in content
            trigger_words = [w.strip().lower() for w in c.trigger_event.split() if len(w) > 3]
            match_count = sum(1 for w in trigger_words if w in content_lower)
            if trigger_words and match_count / len(trigger_words) > 0.4:
                c.status = "active"
                logger.info("Conflict %s activated at chapter %d", c.conflict_id, chapter_number)
        elif c.status == "active":
            # Check for escalation keywords
            escalation_words = ["phản bội", "đối đầu", "bùng nổ", "không thể tha thứ", "quyết chiến"]
            if any(w in content_lower for w in escalation_words):
                c.status = "escalating"
    return conflicts
