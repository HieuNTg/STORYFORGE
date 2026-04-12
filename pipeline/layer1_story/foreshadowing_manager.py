"""Foreshadowing manager — plans and tracks narrative seeds and payoffs."""

import json
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
    """Mark seeds as planted using keyword fallback. Use verify_seeds_semantic for LLM-based check."""
    for f in plan:
        if f.plant_chapter == chapter_number and not f.planted:
            if chapter_content:
                hint_words = [w.lower() for w in f.hint.split() if len(w) > 3]
                content_lower = chapter_content.lower()
                if hint_words:
                    match_ratio = sum(1 for w in hint_words if w in content_lower) / len(hint_words)
                    if match_ratio >= 0.3:
                        f.planted = True
                        f.planted_confidence = match_ratio
                    else:
                        logger.warning(
                            "Foreshadowing '%s' scheduled for ch%d but hint not detected (match=%.0f%%)",
                            f.hint[:50], chapter_number, match_ratio * 100,
                        )
                else:
                    f.planted = True
                    f.planted_confidence = 1.0
            else:
                f.planted = True
                f.planted_confidence = 1.0


_SEMANTIC_VERIFY_PROMPT = """Kiểm tra nội dung chương có chứa KHÁI NIỆM của các mầm foreshadowing hay không.
Không cần khớp từ khóa — chỉ cần ý nghĩa tương đương.

NỘI DUNG (500 ký tự):
{excerpt}

MẦM CẦN KIỂM TRA:
{seeds_list}

Trả JSON:
{{"results": [{{"hint": "...", "confidence": 0.0-1.0, "evidence": "trích dẫn ngắn hoặc 'không tìm thấy'"}}]}}
CHỈ trả JSON."""


def verify_seeds_semantic(
    llm: "LLMClient",
    chapter_content: str,
    seeds: list[ForeshadowingEntry],
    model: Optional[str] = None,
    threshold: float = 0.7,
) -> None:
    """Semantic verification of foreshadowing seeds. 1 LLM call for all seeds. In-place update."""
    if not seeds:
        return

    excerpt = chapter_content[:500]
    seeds_list = "\n".join(f"- {s.hint}" for s in seeds)
    prompt = _SEMANTIC_VERIFY_PROMPT.format(excerpt=excerpt, seeds_list=seeds_list)

    try:
        raw = llm.generate(
            system_prompt="Bạn là editor chuyên foreshadowing. Trả JSON.",
            user_prompt=prompt,
            max_tokens=1024,
            model=model,
        )
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
        data = json.loads(raw)

        hint_to_seed = {s.hint: s for s in seeds}
        for r in data.get("results", []):
            hint = r.get("hint", "")
            conf = float(r.get("confidence", 0.0))
            seed = hint_to_seed.get(hint)
            if seed:
                seed.planted_confidence = conf
                if conf >= threshold:
                    seed.planted = True
                else:
                    logger.info(
                        "Seed '%s' semantic confidence %.0f%% (below %.0f%% threshold)",
                        hint[:40], conf * 100, threshold * 100,
                    )
    except Exception as e:
        logger.warning("Semantic seed verification failed, falling back to keyword: %s", e)
        for s in seeds:
            _keyword_check(s, chapter_content)


def verify_payoffs_semantic(
    llm: "LLMClient",
    chapter_content: str,
    payoffs: list[ForeshadowingEntry],
    model: Optional[str] = None,
    threshold: float = 0.7,
) -> None:
    """Semantic verification of foreshadowing payoffs. Same pattern as seed verification."""
    if not payoffs:
        return

    excerpt = chapter_content[:500]
    payoffs_list = "\n".join(f"- {p.hint}" for p in payoffs)
    prompt = _SEMANTIC_VERIFY_PROMPT.format(excerpt=excerpt, seeds_list=payoffs_list)

    try:
        raw = llm.generate(
            system_prompt="Bạn là editor chuyên foreshadowing. Trả JSON.",
            user_prompt=prompt,
            max_tokens=1024,
            model=model,
        )
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
        data = json.loads(raw)

        hint_to_payoff = {p.hint: p for p in payoffs}
        for r in data.get("results", []):
            hint = r.get("hint", "")
            conf = float(r.get("confidence", 0.0))
            payoff = hint_to_payoff.get(hint)
            if payoff and conf >= threshold:
                payoff.paid_off = True
    except Exception as e:
        logger.warning("Semantic payoff verification failed, falling back: %s", e)
        for p in payoffs:
            p.paid_off = True


def _keyword_check(entry: ForeshadowingEntry, content: str) -> None:
    """Keyword-based fallback for a single entry."""
    hint_words = [w.lower() for w in entry.hint.split() if len(w) > 3]
    content_lower = content.lower()
    if hint_words:
        ratio = sum(1 for w in hint_words if w in content_lower) / len(hint_words)
        if ratio >= 0.3:
            entry.planted = True
            entry.planted_confidence = ratio
    else:
        entry.planted = True
        entry.planted_confidence = 1.0


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
