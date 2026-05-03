"""Sprint 3 Task 3 — Cross-chapter ArcMilestone contract.

Generates arc-level milestones from MacroArcs (what must happen per arc), checks
them against chapter content via keyword heuristics, and produces a drift audit
that flags arcs with missed beats. Complements per-chapter/per-character arc
validation in `arc_execution_validator` with a broader structural view.

Design choices (YAGNI):
- Heuristic check only (keyword match across chapter content). LLM validation
  deferred; milestones are derived from LLM-generated descriptions + keywords,
  so the plan itself captures signal.
- Milestones are content-agnostic beats (not character-specific) — keep separate
  from arc_waypoints which are character-centric.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from models.schemas import ArcMilestone, Chapter, MacroArc

if TYPE_CHECKING:
    from services.llm_client import LLMClient

logger = logging.getLogger(__name__)


_GENERATE_PROMPT = """\
Bạn là biên kịch cấu trúc truyện. Cho các macro arc sau, sinh ra 2-3 MILESTONE
cho mỗi arc — những sự kiện then chốt BẮT BUỘC phải xảy ra để arc có ý nghĩa.

Synopsis: {synopsis}
Genre: {genre}

Macro arcs:
{arcs}

Trả về JSON:
{{
  "milestones": [
    {{
      "milestone_id": "m1_a1",
      "arc_number": 1,
      "description": "Mô tả sự kiện cốt lõi",
      "required_by_chapter": 3,
      "keywords": ["từ khóa 1", "từ khóa 2", "từ khóa 3"],
      "characters_involved": ["Tên nhân vật"]
    }}
  ]
}}

Quy tắc:
- milestone_id phải unique, định dạng m{{N}}_a{{arc_number}}
- required_by_chapter phải nằm trong [chapter_start, chapter_end] của arc
- keywords: 3-5 từ/cụm từ tiếng Việt đặc trưng cho milestone (để heuristic match)
- 2-3 milestones mỗi arc, tối đa 3"""


def generate_arc_milestones(
    llm: "LLMClient",
    macro_arcs: list[MacroArc],
    synopsis: str,
    genre: str,
    model: Optional[str] = None,
) -> list[ArcMilestone]:
    """Ask LLM for milestones per arc. Returns validated ArcMilestone list."""
    if not macro_arcs:
        return []

    arcs_text = "\n".join(
        f"- Arc {a.arc_number} '{a.name}' (ch{a.chapter_start}-{a.chapter_end}): "
        f"conflict={a.central_conflict}; focus={','.join(a.character_focus)}"
        for a in macro_arcs
    )

    try:
        result = llm.generate_json(
            system_prompt="Bạn là biên kịch cấu trúc truyện. BẮT BUỘC tiếng Việt. Trả về JSON.",
            user_prompt=_GENERATE_PROMPT.format(
                synopsis=synopsis[:800], genre=genre, arcs=arcs_text,
            ),
            temperature=0.5,
            model=model,
        )
    except Exception as e:
        logger.warning("Arc milestone generation failed: %s", e)
        return []

    milestones: list[ArcMilestone] = []
    arc_bounds = {a.arc_number: (a.chapter_start, a.chapter_end) for a in macro_arcs}
    for raw in result.get("milestones", []):
        if not isinstance(raw, dict):
            continue
        try:
            m = ArcMilestone(**raw)
            # Clamp required_by_chapter to arc bounds
            lo, hi = arc_bounds.get(m.arc_number, (1, 10_000))
            if not (lo <= m.required_by_chapter <= hi):
                logger.warning(
                    "Milestone %s required_by_chapter=%d outside arc range [%d,%d] — clamping",
                    m.milestone_id, m.required_by_chapter, lo, hi,
                )
                m.required_by_chapter = max(lo, min(hi, m.required_by_chapter))
            milestones.append(m)
        except Exception as e:
            logger.warning("Skipping malformed milestone %s: %s", raw, e)
    return milestones


def check_milestones_in_chapter(
    milestones: list[ArcMilestone],
    chapter: Chapter,
) -> list[ArcMilestone]:
    """Heuristic check: mark milestones as 'hit' if keywords appear in chapter.

    Mutates milestones in place and returns the list of newly-hit milestones.
    A milestone is 'hit' when >=2 of its keywords (or >=1 if only 1 keyword) appear.
    """
    newly_hit: list[ArcMilestone] = []
    content_lower = chapter.content.lower()
    for m in milestones:
        if m.status != "pending":
            continue
        if not m.keywords:
            continue
        matches = [kw for kw in m.keywords if kw.lower() in content_lower]
        required_matches = 1 if len(m.keywords) <= 1 else 2
        if len(matches) >= required_matches:
            m.status = "hit"
            m.hit_chapter = chapter.chapter_number
            m.confidence = min(1.0, len(matches) / max(1, len(m.keywords)))
            # Evidence: 60-char window around first match
            idx = content_lower.find(matches[0].lower())
            start = max(0, idx - 30)
            end = min(len(chapter.content), idx + len(matches[0]) + 30)
            m.evidence = chapter.content[start:end].strip()
            newly_hit.append(m)
    return newly_hit


def audit_arc_milestones(
    milestones: list[ArcMilestone],
    final_chapter: int,
) -> dict:
    """Aggregate milestone status; mark overdue pendings as 'missed'.

    Returns a dict suitable for StoryDraft.arc_milestone_audit with per-arc
    stats and an overall drift_rate.
    """
    by_arc: dict[int, dict] = {}
    for m in milestones:
        if m.status == "pending" and m.required_by_chapter <= final_chapter:
            m.status = "missed"
        rec = by_arc.setdefault(m.arc_number, {"hit": 0, "missed": 0, "pending": 0, "total": 0})
        rec[m.status] = rec.get(m.status, 0) + 1
        rec["total"] += 1

    total = len(milestones)
    hit = sum(1 for m in milestones if m.status == "hit")
    missed = sum(1 for m in milestones if m.status == "missed")
    pending = sum(1 for m in milestones if m.status == "pending")

    return {
        "total": total,
        "hit": hit,
        "missed": missed,
        "pending": pending,
        "hit_rate": (hit / total) if total else 0.0,
        "drift_rate": (missed / total) if total else 0.0,
        "by_arc": by_arc,
    }


def format_milestone_warnings(audit: dict) -> list[str]:
    """Format audit dict as user-facing warning strings."""
    lines: list[str] = []
    if audit.get("total", 0) == 0:
        return lines
    drift = audit.get("drift_rate", 0.0)
    if drift > 0:
        lines.append(
            f"⚠️ Arc milestones: {audit['missed']}/{audit['total']} missed "
            f"(drift rate {drift:.0%})"
        )
    for arc_num, rec in audit.get("by_arc", {}).items():
        if rec.get("missed", 0) > 0:
            lines.append(
                f"  • Arc {arc_num}: {rec['missed']}/{rec['total']} beats missed"
            )
    if audit.get("hit", 0) and drift == 0:
        lines.append(f"✅ Arc milestones: {audit['hit']}/{audit['total']} hit")
    return lines
