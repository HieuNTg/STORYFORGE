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
            if payoff:
                # Store confidence on entry (reuse planted_confidence slot for payoff too)
                payoff.planted_confidence = max(payoff.planted_confidence or 0.0, conf)
                if conf >= threshold:
                    payoff.paid_off = True
                else:
                    logger.info(
                        "Payoff '%s' semantic confidence %.0f%% (below %.0f%% threshold)",
                        hint[:40], conf * 100, threshold * 100,
                    )
    except Exception as e:
        # Bug fix: previously blindly marked all as paid_off on LLM failure.
        # Fall back to keyword check so unpaid stays unpaid.
        logger.warning("Semantic payoff verification failed, keyword fallback: %s", e)
        for p in payoffs:
            _keyword_check(p, chapter_content)
            # _keyword_check sets .planted; copy to .paid_off when matched
            if p.planted_confidence and p.planted_confidence >= 0.3:
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


# ══════════════════════════════════════════════════════════════════════════════
# Phase 6: Foreshadowing Payoff Enforcement
# ══════════════════════════════════════════════════════════════════════════════


def get_overdue_payoffs(
    plan: list[ForeshadowingEntry],
    current_chapter: int,
    grace_chapters: int = 2,
) -> list[ForeshadowingEntry]:
    """Get foreshadowing that should have paid off but hasn't.

    Args:
        plan: Full foreshadowing plan
        current_chapter: Current chapter being written
        grace_chapters: How many chapters past deadline before flagging
    """
    overdue = []
    for f in plan:
        if f.planted and not f.paid_off:
            if f.payoff_chapter + grace_chapters < current_chapter:
                overdue.append(f)
    return overdue


def get_approaching_payoffs(
    plan: list[ForeshadowingEntry],
    current_chapter: int,
    lookahead: int = 3,
) -> list[ForeshadowingEntry]:
    """Get payoffs that are approaching (within lookahead chapters)."""
    approaching = []
    for f in plan:
        if f.planted and not f.paid_off:
            chapters_until = f.payoff_chapter - current_chapter
            if 0 < chapters_until <= lookahead:
                approaching.append(f)
    return approaching


def get_payoff_urgency(
    entry: ForeshadowingEntry,
    current_chapter: int,
) -> str:
    """Calculate urgency level for a payoff."""
    if entry.paid_off:
        return "done"
    if not entry.planted:
        return "not_planted"

    chapters_until = entry.payoff_chapter - current_chapter

    if chapters_until < 0:
        return "overdue"
    elif chapters_until == 0:
        return "now"
    elif chapters_until <= 2:
        return "urgent"
    elif chapters_until <= 5:
        return "soon"
    else:
        return "later"


def format_payoff_enforcement_prompt(
    overdue: list[ForeshadowingEntry],
    approaching: list[ForeshadowingEntry],
    current_chapter: int,
) -> str:
    """Format enforcement prompt for chapter writer.

    Stronger language for overdue payoffs, reminder for approaching ones.
    """
    lines = []

    if overdue:
        lines.append("## ⚠️ FORESHADOWING QUÁ HẠN - BẮT BUỘC PAYOFF:")
        for f in overdue:
            delay = current_chapter - f.payoff_chapter
            lines.append(
                f"- 🚨 '{f.hint}' (gieo ch.{f.plant_chapter}, "
                f"hẹn ch.{f.payoff_chapter}, trễ {delay} chương) — PHẢI PAYOFF NGAY!"
            )
        lines.append("")

    if approaching:
        lines.append("## 📌 FORESHADOWING SẮP ĐẾN HẠN:")
        for f in approaching:
            remaining = f.payoff_chapter - current_chapter
            lines.append(
                f"- ⏰ '{f.hint}' (gieo ch.{f.plant_chapter}) → "
                f"payoff ch.{f.payoff_chapter} (còn {remaining} chương)"
            )

    return "\n".join(lines) if lines else ""


def audit_foreshadowing_plan(
    plan: list[ForeshadowingEntry],
    total_chapters: int,
) -> dict:
    """Audit foreshadowing plan at end of story. Returns summary."""
    total = len(plan)
    if total == 0:
        return {
            "total": 0,
            "planted": 0,
            "paid_off": 0,
            "missed": 0,
            "not_planted": 0,
            "completion_rate": 1.0,
            "missed_payoffs": [],
            "unplanted_seeds": [],
        }

    planted = sum(1 for f in plan if f.planted)
    paid_off = sum(1 for f in plan if f.paid_off)
    missed = [f for f in plan if f.planted and not f.paid_off]
    not_planted = [f for f in plan if not f.planted]

    completion_rate = paid_off / total if total > 0 else 1.0

    return {
        "total": total,
        "planted": planted,
        "paid_off": paid_off,
        "missed": len(missed),
        "not_planted": len(not_planted),
        "completion_rate": completion_rate,
        "missed_payoffs": [
            {
                "hint": f.hint[:50],
                "plant_chapter": f.plant_chapter,
                "payoff_chapter": f.payoff_chapter,
                "characters": f.characters_involved,
            }
            for f in missed
        ],
        "unplanted_seeds": [
            {
                "hint": f.hint[:50],
                "plant_chapter": f.plant_chapter,
            }
            for f in not_planted
        ],
    }


def format_audit_warnings(audit: dict) -> list[str]:
    """Format audit results as warning strings."""
    warnings = []

    if audit["missed"] > 0:
        warnings.append(
            f"⚠️ {audit['missed']} foreshadowing đã gieo nhưng chưa payoff"
        )
        for m in audit["missed_payoffs"][:5]:
            warnings.append(
                f"  - '{m['hint']}' (ch.{m['plant_chapter']}→ch.{m['payoff_chapter']})"
            )

    if audit["not_planted"] > 0:
        warnings.append(
            f"⚠️ {audit['not_planted']} foreshadowing không được gieo"
        )
        for u in audit["unplanted_seeds"][:3]:
            warnings.append(f"  - '{u['hint']}' (planned ch.{u['plant_chapter']})")

    rate = audit["completion_rate"]
    if rate < 0.8:
        warnings.append(
            f"🚨 Tỷ lệ hoàn thành foreshadowing thấp: {rate:.0%}"
        )

    return warnings


def get_foreshadowing_status(
    plan: list[ForeshadowingEntry],
    chapter_number: int,
) -> str:
    """Bug #5: Get foreshadowing status summary for prompt injection.

    Returns a formatted string showing:
    - Seeds planted in previous chapters (waiting for payoff)
    - Payoffs already delivered
    - Seeds to plant this chapter
    - Payoffs due this chapter
    """
    if not plan:
        return ""

    planted_waiting = []
    paid_off = []
    to_plant = []
    to_payoff = []

    for f in plan:
        if f.plant_chapter < chapter_number and f.planted:
            if f.paid_off:
                paid_off.append(f)
            else:
                planted_waiting.append(f)
        if f.plant_chapter == chapter_number and not f.planted:
            to_plant.append(f)
        if f.payoff_chapter == chapter_number and not f.paid_off:
            to_payoff.append(f)

    lines = []
    if planted_waiting:
        lines.append("## FORESHADOWING ĐÃ GIEO (chờ payoff):")
        for f in planted_waiting[:5]:
            lines.append(f"- Ch{f.plant_chapter}: \"{f.hint}\" → payoff ch{f.payoff_chapter}")

    if to_plant:
        lines.append("## CẦN GIEO CHƯƠNG NÀY:")
        for f in to_plant:
            lines.append(f"- \"{f.hint}\"")

    if to_payoff:
        lines.append("## CẦN PAYOFF CHƯƠNG NÀY:")
        for f in to_payoff:
            lines.append(f"- \"{f.hint}\" (đã gieo ch{f.plant_chapter})")

    return "\n".join(lines) if lines else ""


def suggest_late_payoff_chapter(
    entry: ForeshadowingEntry,
    current_chapter: int,
    total_chapters: int,
) -> int:
    """Suggest best chapter for late payoff if original deadline missed."""
    remaining = total_chapters - current_chapter
    if remaining <= 0:
        return current_chapter  # Must be now

    # For overdue payoffs, suggest next 2-3 chapters
    # but avoid cramming at the very end
    ideal_chapter = current_chapter + min(2, remaining // 2)
    return min(ideal_chapter, total_chapters - 1)  # Leave room for finale


def reschedule_overdue_payoffs(
    plan: list[ForeshadowingEntry],
    current_chapter: int,
    total_chapters: int,
) -> list[tuple[ForeshadowingEntry, int]]:
    """Reschedule overdue payoffs to new chapters. Returns [(entry, new_chapter)]."""
    overdue = get_overdue_payoffs(plan, current_chapter, grace_chapters=0)
    rescheduled = []

    for i, f in enumerate(overdue):
        # Spread out rescheduled payoffs
        new_ch = suggest_late_payoff_chapter(f, current_chapter + i, total_chapters)
        f.payoff_chapter = new_ch
        rescheduled.append((f, new_ch))
        logger.info(
            "Rescheduled payoff '%s' to ch%d (was ch%d)",
            f.hint[:40], new_ch, f.payoff_chapter,
        )

    return rescheduled
