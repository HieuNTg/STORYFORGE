"""Critique-revise loop for chapter outlines after initial generation."""

import logging
from typing import Optional, TYPE_CHECKING

from models.schemas import Character, WorldSetting, ChapterOutline

if TYPE_CHECKING:
    from services.llm_client import LLMClient

logger = logging.getLogger(__name__)

REVISION_THRESHOLD = 4  # revise if overall_score < this

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

CRITIQUE_OUTLINE = """Bạn là biên tập viên kịch bản. Phân tích dàn ý và chỉ ra vấn đề.
Thể loại: {genre} | Tóm tắt: {synopsis}
Nhân vật: {characters}
Bối cảnh: {world}
Dàn ý: {outlines}

Đánh giá: plot_holes (lỗ hổng logic), pacing_issues (nhịp điệu sai, vd 3 climax liên tiếp), character_underuse (nhân vật biến mất quá lâu), arc_coherence (arc không tự nhiên), foreshadowing_gaps (seed không payoff hoặc ngược lại), overall_score 1-5.
BẮT BUỘC tiếng Việt. Trả về JSON:
{{"plot_holes":[],"pacing_issues":[],"character_underuse":[],"arc_coherence":[],"foreshadowing_gaps":[],"overall_score":3}}"""

REVISE_OUTLINE = """Bạn là biên kịch tài năng. Sửa dàn ý dựa trên phản hồi biên tập.
Thể loại: {genre} | Nhân vật: {characters} | Bối cảnh: {world}
Dàn ý gốc: {outlines}
Phản hồi: lỗ hổng=[{plot_holes}] nhịp điệu=[{pacing_issues}] nhân vật lãng quên=[{character_underuse}] arc=[{arc_coherence}] foreshadowing=[{foreshadowing_gaps}]

Yêu cầu: giữ nguyên số chương, chỉ sửa phần có vấn đề. Đảm bảo setup→rising→climax→cooldown xen kẽ. Bổ sung seed/payoff còn thiếu. Lấp lỗ hổng logic.
BẮT BUỘC tiếng Việt. Tên nhân vật PHẢI dùng CHÍNH XÁC như trên.
Trả về JSON:
{{"outlines":[{{"chapter_number":1,"title":"","summary":"","key_events":[],"characters_involved":[],"emotional_arc":"","pacing_type":"rising","arc_id":1,"foreshadowing_plants":[],"payoff_references":[]}}]}}"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_outlines_for_prompt(outlines: list[ChapterOutline]) -> str:
    lines = []
    for o in outlines:
        lines.append(
            f"Chương {o.chapter_number} [{o.pacing_type}] '{o.title}': {o.summary} "
            f"| Nhân vật: {', '.join(o.characters_involved)} "
            f"| Arc ID: {o.arc_id}"
        )
    return "\n".join(lines)


def _format_critique_field(items) -> str:
    if not items:
        return "Không có"
    if isinstance(items, list):
        return "; ".join(str(i) for i in items)
    return str(items)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def critique_outline(
    llm: "LLMClient",
    outlines: list[ChapterOutline],
    characters: list[Character],
    world: WorldSetting,
    synopsis: str,
    genre: str,
    model: Optional[str] = None,
) -> dict:
    """Call LLM to critique the outline. Returns critique dict. Non-fatal."""
    chars_text = "\n".join(
        f"- {c.name} ({c.role}): {c.personality}" for c in characters
    )
    try:
        result = llm.generate_json(
            system_prompt="Bạn là biên tập viên kịch bản chuyên nghiệp. BẮT BUỘC viết bằng tiếng Việt. Trả về JSON.",
            user_prompt=CRITIQUE_OUTLINE.format(
                genre=genre,
                synopsis=synopsis,
                characters=chars_text,
                world=f"{world.name}: {world.description}",
                outlines=_format_outlines_for_prompt(outlines),
            ),
            model=model,
        )
        return result if isinstance(result, dict) else {}
    except Exception as e:
        logger.warning("critique_outline failed (non-fatal): %s", e)
        return {}


def revise_outline_from_critique(
    llm: "LLMClient",
    outlines: list[ChapterOutline],
    critique: dict,
    characters: list[Character],
    world: WorldSetting,
    genre: str,
    threshold: int = REVISION_THRESHOLD,
    model: Optional[str] = None,
) -> list[ChapterOutline]:
    """Revise outlines if critique score is below threshold. Non-fatal."""
    score = critique.get("overall_score", threshold)
    try:
        score = int(score)
    except (TypeError, ValueError):
        score = threshold

    if score >= threshold:
        logger.info("Outline score %s >= threshold %s, skipping revision.", score, threshold)
        return outlines

    chars_text = "\n".join(
        f"- {c.name} ({c.role}): {c.personality}" for c in characters
    )
    try:
        result = llm.generate_json(
            system_prompt="Bạn là biên kịch tài năng. BẮT BUỘC viết bằng tiếng Việt. Trả về JSON.",
            user_prompt=REVISE_OUTLINE.format(
                genre=genre,
                characters=chars_text,
                world=f"{world.name}: {world.description}",
                outlines=_format_outlines_for_prompt(outlines),
                plot_holes=_format_critique_field(critique.get("plot_holes", [])),
                pacing_issues=_format_critique_field(critique.get("pacing_issues", [])),
                character_underuse=_format_critique_field(critique.get("character_underuse", [])),
                arc_coherence=_format_critique_field(critique.get("arc_coherence", [])),
                foreshadowing_gaps=_format_critique_field(critique.get("foreshadowing_gaps", [])),
            ),
            temperature=0.85,
            model=model,
        )
        revised = [ChapterOutline(**o) for o in result.get("outlines", [])]
        if not revised:
            logger.warning("revise_outline_from_critique returned empty list, keeping originals.")
            return outlines
        logger.info("Outline revised: %d chapters (score was %s).", len(revised), score)
        return revised
    except Exception as e:
        logger.warning("revise_outline_from_critique failed (non-fatal): %s", e)
        return outlines


def critique_and_revise(
    llm: "LLMClient",
    outlines: list[ChapterOutline],
    characters: list[Character],
    world: WorldSetting,
    synopsis: str,
    genre: str,
    max_rounds: int = 1,
    model: Optional[str] = None,
) -> tuple[list[ChapterOutline], dict]:
    """Critique then optionally revise outlines. Returns (outlines, critique)."""
    critique: dict = {}
    for round_num in range(max_rounds):
        critique = critique_outline(llm, outlines, characters, world, synopsis, genre, model=model)
        if not critique:
            logger.warning("Round %d: empty critique, stopping.", round_num + 1)
            break
        score = critique.get("overall_score", REVISION_THRESHOLD)
        logger.info("Round %d critique score: %s", round_num + 1, score)
        outlines = revise_outline_from_critique(
            llm, outlines, critique, characters, world, genre, model=model
        )
        try:
            if int(score) >= REVISION_THRESHOLD:
                break
        except (TypeError, ValueError):
            break
    return outlines, critique
