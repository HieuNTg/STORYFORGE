"""Chapter-level self-critique after writing — targeted quality dimensions for Layer 1."""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.llm_client import LLMClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt templates (Vietnamese)
# ---------------------------------------------------------------------------

CRITIQUE_CHAPTER = """\
Bạn là biên tập viên văn học chuyên nghiệp. Hãy đánh giá chương truyện sau theo các tiêu chí cụ thể.

## Thông tin truyện
- Thể loại: {genre}
- Nhịp độ mục tiêu: {pacing_type}
- Nhân vật chính: {characters}

## Dàn ý chương
{outline}

## Nội dung chương
{content}

## Nhiệm vụ
Đánh giá chương theo đúng 5 tiêu chí sau. Trả về JSON hợp lệ, không có gì ngoài JSON.

{{
  "voice_consistency": {{
    "score": <1-5>,
    "notes": "<nhân vật có giọng nói riêng biệt không? Ai bị mờ nhạt?>"
  }},
  "pacing_match": {{
    "score": <1-5>,
    "notes": "<nhịp độ thực tế có khớp với '{pacing_type}' không?>"
  }},
  "plot_advancement": {{
    "score": <1-5>,
    "notes": "<chương có thực sự đẩy cốt truyện tiến không? Điều gì thay đổi?>"
  }},
  "sensory_richness": {{
    "score": <1-5>,
    "notes": "<có đủ show-don't-tell, chi tiết cảm giác, hình ảnh cụ thể không?>"
  }},
  "cliffhanger_quality": {{
    "score": <1-5>,
    "notes": "<kết chương có tạo móc kéo người đọc sang chương tiếp không?>"
  }},
  "weak_sections": [
    {{
      "location": "<beginning|middle|end>",
      "issue": "<mô tả vấn đề cụ thể>"
    }}
  ]
}}

Chấm điểm: 1=rất yếu, 2=yếu, 3=trung bình, 4=tốt, 5=xuất sắc.
weak_sections chỉ liệt kê phần thực sự có vấn đề (score < 3), có thể để mảng rỗng.
"""

REWRITE_WEAK_SECTION = """\
Bạn là nhà văn chuyên nghiệp. Hãy viết lại một phần yếu của chương truyện.

## Vấn đề cần sửa
- Vị trí: {location} (phần {location} của chương)
- Vấn đề: {issue}

## Toàn bộ chương (để hiểu ngữ cảnh)
{content}

## Nhiệm vụ
Viết lại phần {location} của chương để khắc phục vấn đề trên.
- Giữ nguyên các sự kiện và nhân vật
- Chỉ cải thiện cách thể hiện, không thay đổi cốt truyện
- Độ dài tương đương phần gốc
- Trả về TOÀN BỘ chương đã được chỉnh sửa (không chỉ phần được sửa)
- Không có chú thích hay giải thích, chỉ trả về nội dung chương
"""

# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def critique_chapter(
    llm: "LLMClient",
    content: str,
    outline: str,
    characters: list,
    genre: str,
    pacing_type: str,
    model: str | None = None,
) -> dict:
    """Critique a chapter on five targeted dimensions.

    Returns critique dict on success, empty dict on failure (non-fatal).
    """
    char_names = ", ".join(
        c.name if hasattr(c, "name") else str(c) for c in characters
    ) if characters else "không xác định"

    system_prompt = "Bạn là biên tập viên văn học. Trả về JSON hợp lệ, không markdown."
    user_prompt = CRITIQUE_CHAPTER.format(
        genre=genre or "không xác định",
        pacing_type=pacing_type or "bình thường",
        characters=char_names,
        outline=outline or "",
        content=content,
    )

    try:
        result = llm.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            model_tier="cheap",
        )
        if isinstance(result, dict):
            return result
        logger.warning("critique_chapter: unexpected LLM response type %s", type(result))
        return {}
    except Exception as exc:
        logger.warning("critique_chapter failed (non-fatal): %s", exc)
        return {}


def rewrite_weak_sections(
    llm: "LLMClient",
    content: str,
    critique: dict,
    max_rewrites: int = 2,
    model: str | None = None,
) -> str:
    """Rewrite sections scoring below 2.5, up to max_rewrites (lowest scores first).

    Returns updated content, or original content on failure (non-fatal).
    """
    if not critique or not content:
        return content

    DIMS = ("voice_consistency", "pacing_match", "plot_advancement", "sensory_richness", "cliffhanger_quality")
    scored = []
    for dim in DIMS:
        e = critique.get(dim, {})
        if isinstance(e, dict) and e.get("score") is not None:
            try:
                scored.append((float(e["score"]), dim, e))
            except (TypeError, ValueError):
                pass
    weak_sections = critique.get("weak_sections", []) if isinstance(critique.get("weak_sections"), list) else []
    to_rewrite = sorted([s for s in scored if s[0] < 2.5], key=lambda x: x[0])[:max_rewrites]
    if not to_rewrite:
        return content

    _LOC = {"sensory_richness": "beginning", "cliffhanger_quality": "end"}
    current_content = content
    rewrites_done = 0

    for score, dim, entry in to_rewrite:
        if rewrites_done >= max_rewrites:
            break
        location = _LOC.get(dim, "middle")
        for ws in weak_sections:
            if isinstance(ws, dict) and ws.get("location"):
                location = ws["location"]
                break
        issue = entry.get("notes") or f"Điểm thấp ({score:.1f}/5) cho tiêu chí: {dim}"

        system_prompt = "Bạn là nhà văn chuyên nghiệp. Chỉ trả về nội dung chương, không có gì khác."
        user_prompt = REWRITE_WEAK_SECTION.format(
            location=location,
            issue=issue,
            content=current_content,
        )

        try:
            rewritten = llm.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model,
                max_tokens=8192,
            )
            if isinstance(rewritten, str) and len(rewritten) > 100:
                current_content = rewritten
                rewrites_done += 1
                logger.debug("rewrite_weak_sections: rewrote '%s' (score %.1f)", dim, score)
            else:
                logger.warning(
                    "rewrite_weak_sections: short/empty response for '%s', skipping", dim
                )
        except Exception as exc:
            logger.warning("rewrite_weak_sections failed for '%s' (non-fatal): %s", dim, exc)

    return current_content


def should_critique(
    chapter_number: int,
    total_chapters: int,
    macro_arcs=None,
    pacing_type: str = "",
) -> bool:
    """Selective critique: first/last 3, arc boundaries, climax/twist chapters.

    Expected: ~15-25% of chapters critiqued in a 100-chapter story.
    Short stories (<=20): always critique.
    """
    if total_chapters <= 20:
        return True
    if chapter_number <= 3 or chapter_number >= total_chapters - 2:
        return True
    if pacing_type in ("climax", "twist"):
        return True
    if macro_arcs:
        for arc in macro_arcs:
            start = getattr(arc, "chapter_start", 0)
            end = getattr(arc, "chapter_end", 0)
            if chapter_number == start or chapter_number == end:
                return True
            if chapter_number == start + 1 or chapter_number == end - 1:
                return True
    return False
