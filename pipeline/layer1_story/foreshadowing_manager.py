"""Foreshadowing manager — plans and tracks narrative seeds and payoffs."""

import logging
from typing import Optional, TYPE_CHECKING

from models.schemas import ForeshadowingEntry, MacroArc, ConflictEntry
from services import prompts

if TYPE_CHECKING:
    from services.llm_client import LLMClient

logger = logging.getLogger(__name__)


def generate_foreshadowing_plan(
    llm: "LLMClient",
    title: str,
    genre: str,
    synopsis: str,
    macro_arcs: list[MacroArc],
    conflict_web: list[ConflictEntry],
    model: Optional[str] = None,
) -> list[ForeshadowingEntry]:
    """Generate foreshadowing plan for the entire story."""
    from pipeline.layer1_story.macro_outline_builder import format_arcs_for_prompt
    from pipeline.layer1_story.conflict_web_builder import format_conflicts_for_prompt

    result = llm.generate_json(
        system_prompt="Bạn là bậc thầy foreshadowing. BẮT BUỘC viết bằng tiếng Việt. Trả về JSON.",
        user_prompt=prompts.GENERATE_FORESHADOWING_PLAN.format(
            genre=genre, title=title, synopsis=synopsis,
            macro_arcs=format_arcs_for_prompt(macro_arcs),
            conflict_web=format_conflicts_for_prompt(conflict_web),
        ),
        temperature=0.8,
        model=model,
    )
    entries = []
    for f in result.get("foreshadowing", []):
        if isinstance(f, dict):
            try:
                entries.append(ForeshadowingEntry(**f))
            except Exception as e:
                logger.warning("Skipping malformed foreshadowing: %s", e)
    return entries


def get_seeds_to_plant(plan: list[ForeshadowingEntry], chapter_number: int) -> list[ForeshadowingEntry]:
    """Get foreshadowing seeds that should be planted in this chapter."""
    return [f for f in plan if f.plant_chapter == chapter_number and not f.planted]


def get_payoffs_due(plan: list[ForeshadowingEntry], chapter_number: int) -> list[ForeshadowingEntry]:
    """Get foreshadowing that should pay off in this chapter."""
    return [f for f in plan if f.payoff_chapter == chapter_number and f.planted and not f.paid_off]


def mark_planted(
    plan: list[ForeshadowingEntry],
    chapter_number: int,
    chapter_content: str = "",
) -> None:
    """Mark seeds as planted. If chapter_content provided, verify hint actually appears."""
    for f in plan:
        if f.plant_chapter == chapter_number and not f.planted:
            if chapter_content:
                # Verify hint concept appears in chapter (simple substring or key word check)
                hint_words = [w.lower() for w in f.hint.split() if len(w) > 3]
                content_lower = chapter_content.lower()
                # Consider planted if at least 30% of hint key words appear
                if hint_words:
                    match_ratio = sum(1 for w in hint_words if w in content_lower) / len(hint_words)
                    if match_ratio >= 0.3:
                        f.planted = True
                    else:
                        logger.warning(
                            "Foreshadowing '%s' scheduled for ch%d but hint not detected in content (match=%.0f%%)",
                            f.hint[:50], chapter_number, match_ratio * 100,
                        )
                else:
                    f.planted = True  # no key words to check, mark as planted
            else:
                f.planted = True  # no content to verify, mark as planted (backwards compat)


def mark_paid_off(plan: list[ForeshadowingEntry], chapter_number: int) -> None:
    """Mark payoffs as delivered after chapter is written."""
    for f in plan:
        if f.payoff_chapter == chapter_number and f.planted and not f.paid_off:
            f.paid_off = True


def format_seeds_for_prompt(seeds: list[ForeshadowingEntry]) -> str:
    """Format seeds to plant for chapter writing prompt."""
    if not seeds:
        return "Không có foreshadowing cần gieo."
    lines = []
    for s in seeds:
        chars = ", ".join(s.characters_involved) if s.characters_involved else "general"
        lines.append(f"- GIEO: {s.hint} (payoff ở ch.{s.payoff_chapter}, nhân vật: {chars})")
    return "\n".join(lines)


def format_payoffs_for_prompt(payoffs: list[ForeshadowingEntry]) -> str:
    """Format payoffs due for chapter writing prompt."""
    if not payoffs:
        return "Không có foreshadowing cần payoff."
    lines = []
    for p in payoffs:
        lines.append(f"- PAYOFF: {p.hint} (đã gieo ở ch.{p.plant_chapter})")
    return "\n".join(lines)
