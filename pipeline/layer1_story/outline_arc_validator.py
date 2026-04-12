"""Validate outline-to-macro_arc coherence.

One LLM call after outline generation to catch structural misalignments
before chapter writing begins. Non-fatal — returns warnings only.
"""

import logging
from typing import Optional, TYPE_CHECKING

from models.schemas import ChapterOutline, MacroArc

if TYPE_CHECKING:
    from services.llm_client import LLMClient

logger = logging.getLogger(__name__)

_PROMPT = """\
Bạn là biên tập viên kiểm tra tính nhất quán giữa dàn ý chương và cấu trúc arc.

MACRO ARCS:
{arcs_text}

DÀN Ý CHƯƠNG:
{outlines_text}

Hãy kiểm tra:
1. Mỗi arc có ít nhất 1 chương climax không?
2. Chương cuối của mỗi arc có resolution phù hợp không?
3. Chương đầu arc mới có setup đúng không?
4. Arc transitions (chương cuối arc N → chương đầu arc N+1) có mượt không?
5. Character focus của arc có xuất hiện trong các chương thuộc arc đó không?

Trả về JSON:
{{
  "warnings": [
    "Arc 1 (ch1-10) không có chương climax — cần thêm climax vào ch8-10",
    "Chương 11 (đầu Arc 2) không setup xung đột mới"
  ],
  "score": 4.0
}}

Nếu không có vấn đề, trả về {{"warnings": [], "score": 5.0}}"""


def validate_outline_arc_coherence(
    llm: "LLMClient",
    outlines: list[ChapterOutline],
    macro_arcs: list[MacroArc],
    model: Optional[str] = None,
) -> dict:
    """Validate outline-arc alignment. Returns {warnings: list[str], score: float}."""
    if not macro_arcs or not outlines:
        return {"warnings": [], "score": 5.0}

    arcs_text = "\n".join(
        f"- Arc {a.arc_number}: '{a.name}' (ch{a.chapter_start}-{a.chapter_end}) "
        f"| Xung đột: {a.central_conflict} | Nhân vật: {', '.join(a.character_focus)}"
        for a in macro_arcs
    )
    outlines_text = "\n".join(
        f"- Ch{o.chapter_number}: '{o.title}' | Pacing: {o.pacing_type} "
        f"| Nhân vật: {', '.join(o.characters_involved)} | Arc: {o.arc_id}"
        for o in outlines
    )

    try:
        result = llm.generate_json(
            system_prompt="Bạn là biên tập viên phân tích cấu trúc truyện. Trả về JSON bằng tiếng Việt.",
            user_prompt=_PROMPT.format(arcs_text=arcs_text, outlines_text=outlines_text),
            temperature=0.3,
            max_tokens=1000,
            model=model,
        )
    except Exception as e:
        logger.warning("Outline-arc validation failed: %s", e)
        return {"warnings": [], "score": 0.0}

    warnings = result.get("warnings", [])
    score = float(result.get("score", 0.0))

    if warnings:
        logger.info("Outline-arc coherence warnings (%d): %s", len(warnings), "; ".join(warnings[:3]))
    else:
        logger.info("Outline-arc coherence: OK (score=%.1f)", score)

    return {"warnings": warnings, "score": score}
