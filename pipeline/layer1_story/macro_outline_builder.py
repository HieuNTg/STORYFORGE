"""Macro-level story arc builder — creates high-level narrative structure before chapter outlines."""

import logging
from typing import Optional, TYPE_CHECKING

from models.schemas import Character, WorldSetting, MacroArc
from services import prompts

if TYPE_CHECKING:
    from services.llm_client import LLMClient

logger = logging.getLogger(__name__)


def generate_macro_arcs(
    llm: "LLMClient",
    title: str,
    genre: str,
    characters: list[Character],
    world: WorldSetting,
    idea: str,
    num_chapters: int = 100,
    arc_size: int = 30,
    model: Optional[str] = None,
) -> list[MacroArc]:
    """Generate macro-level story arcs that span multiple chapters.

    Each arc has a central conflict, character focus, and emotional trajectory.
    Arcs escalate stakes progressively across the full story.
    """
    chars_text = "\n".join(
        f"- {c.name} ({c.role}): {c.personality}, Động lực: {c.motivation}"
        for c in characters
    )
    result = llm.generate_json(
        system_prompt="Bạn là kiến trúc sư cốt truyện cao cấp. BẮT BUỘC viết bằng tiếng Việt. Trả về JSON.",
        user_prompt=prompts.GENERATE_MACRO_OUTLINE.format(
            genre=genre, title=title, characters=chars_text,
            world=f"{world.name}: {world.description}",
            idea=idea, num_chapters=num_chapters, arc_size=arc_size,
        ),
        temperature=0.85,
        model=model,
    )
    arcs = []
    # Handle LLM returning list directly instead of {macro_arcs} dict
    arc_data = result if isinstance(result, list) else result.get("macro_arcs", [])
    for a in arc_data:
        if isinstance(a, dict):
            try:
                arcs.append(MacroArc(**a))
            except Exception as e:
                logger.warning("Skipping malformed macro arc: %s", e)
    if not arcs:
        # Fallback: single arc covering all chapters
        arcs.append(MacroArc(
            arc_number=1, name="Toàn bộ truyện",
            chapter_start=1, chapter_end=num_chapters,
            central_conflict=idea, character_focus=[c.name for c in characters[:3]],
        ))
    return arcs


def get_arc_for_chapter(arcs: list[MacroArc], chapter_number: int) -> Optional[MacroArc]:
    """Find which macro arc a chapter belongs to."""
    for arc in arcs:
        if arc.chapter_start <= chapter_number <= arc.chapter_end:
            return arc
    return arcs[-1] if arcs else None


def format_arcs_for_prompt(arcs: list[MacroArc]) -> str:
    """Format macro arcs into a prompt-friendly string."""
    lines = []
    for arc in arcs:
        lines.append(
            f"Arc {arc.arc_number} '{arc.name}' (Ch.{arc.chapter_start}-{arc.chapter_end}): "
            f"{arc.central_conflict} | Focus: {', '.join(arc.character_focus)}"
        )
    return "\n".join(lines)
