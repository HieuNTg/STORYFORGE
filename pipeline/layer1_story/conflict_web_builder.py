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
                entry = ConflictEntry(**c)
                if "intensity" in c:
                    entry.intensity = min(5, max(1, int(c["intensity"])))
                conflicts.append(entry)
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
    """Format active conflicts for chapter writing prompt, including intensity."""
    if not conflicts:
        return "Không có xung đột active."
    _INTENSITY_LABELS = {1: "ngầm", 2: "căng thẳng", 3: "gay gắt", 4: "bùng nổ", 5: "đỉnh điểm"}
    lines = []
    for c in conflicts:
        chars = " vs ".join(c.characters) if c.conflict_type != "internal" else c.characters[0]
        status_label = f"{c.status} (ESCALATING)" if c.status == "escalating" else c.status
        intensity_label = _INTENSITY_LABELS.get(c.intensity, f"lv{c.intensity}")
        lines.append(f"- [{c.conflict_type}] {chars}: {c.description} ({status_label}, cường độ: {intensity_label} {c.intensity}/5)")
    return "\n".join(lines)


def update_conflict_status(
    conflicts: list[ConflictEntry],
    chapter_content: str,
    chapter_number: int,
    llm=None,
) -> list[ConflictEntry]:
    """Semantic conflict activation: LLM checks if trigger conditions are met."""
    content_lower = chapter_content.lower()

    dormant_with_triggers = [c for c in conflicts if c.status == "dormant" and c.trigger_event]

    if dormant_with_triggers and llm is not None:
        # Batch check: single LLM call for all dormant conflicts
        conflicts_text = "\n".join(
            f"- conflict_id={c.conflict_id}: trigger=[{c.trigger_event}]"
            for c in dormant_with_triggers
        )
        result = llm.generate_json(
            system_prompt="Bạn phân tích nội dung chương truyện. Trả về JSON.",
            user_prompt=(
                f"Nội dung chương:\n{chapter_content[:3000]}\n\n"
                f"Các xung đột đang dormant:\n{conflicts_text}\n\n"
                "Với mỗi conflict, xác định xem điều kiện trigger có xảy ra trong chương không (theo nghĩa semantic, không cần từ ngữ giống hệt).\n"
                'Trả về JSON: {"activated": ["conflict_id1", "conflict_id2"]}'
            ),
            temperature=0.2,
            max_tokens=300,
            model_tier="cheap",
        )
        activated_ids = set(result.get("activated", []))
        for c in dormant_with_triggers:
            if c.conflict_id in activated_ids:
                c.status = "active"
                logger.info("Conflict %s semantically activated at chapter %d", c.conflict_id, chapter_number)
    elif dormant_with_triggers:
        # Fallback: keyword matching when no LLM available
        for c in dormant_with_triggers:
            trigger_words = [w.strip().lower() for w in c.trigger_event.split() if len(w) > 3]
            match_count = sum(1 for w in trigger_words if w in content_lower)
            if trigger_words and match_count / len(trigger_words) > 0.4:
                c.status = "active"
                logger.info("Conflict %s keyword-activated at chapter %d", c.conflict_id, chapter_number)

    # Escalation check with intensity tracking
    escalation_words = ["phản bội", "đối đầu", "bùng nổ", "không thể tha thứ", "quyết chiến",
                        "giết", "chết", "máu", "chiến tranh", "phá hủy"]
    for c in conflicts:
        if c.status in ("active", "escalating"):
            matched = sum(1 for w in escalation_words if w in content_lower)
            if matched >= 3 and c.intensity < 5:
                c.intensity = min(5, c.intensity + 2)
                c.status = "escalating"
            elif matched >= 1 and c.intensity < 5:
                c.intensity = min(5, c.intensity + 1)
                if c.intensity >= 4:
                    c.status = "escalating"
            c.escalation_timeline.append({"chapter": chapter_number, "intensity": c.intensity})

    return conflicts
