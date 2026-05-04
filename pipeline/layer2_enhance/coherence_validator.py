"""Kiểm tra tính nhất quán xuyên chương sau khi tăng cường Layer 2.

Kiểm tra: timeline, hành vi nhân vật, chuỗi cốt truyện,
quan hệ nhân vật. Không gây lỗi nghiêm trọng — vấn đề được
ghi log và có thể tự động sửa.
"""

import logging
from models.schemas import EnhancedStory, StoryDraft, Chapter, count_words
from pipeline.layer2_enhance._envelope_access import conflict_web as _envelope_conflict_web
from services.llm_client import LLMClient
from services import prompts

logger = logging.getLogger(__name__)


def validate_coherence(
    llm: LLMClient,
    enhanced: EnhancedStory,
    draft: StoryDraft,
) -> list[dict]:
    """Kiểm tra tính nhất quán xuyên chương sau khi tăng cường.

    Trả về danh sách vấn đề phát hiện. Mỗi vấn đề:
    {type, chapter, description, severity, fix_suggestion}
    """
    # Tóm tắt từng chương để LLM phân tích
    chapter_summaries = "\n".join(
        f"Chương {ch.chapter_number} ({ch.title}): "
        f"{ch.summary or ch.content[:200]}"
        for ch in enhanced.chapters
    )

    characters_text = "\n".join(
        f"- {c.name} ({c.role}): {c.personality}"
        for c in draft.characters
    )

    relationships_text = ""
    _conflicts = _envelope_conflict_web(draft)
    if _conflicts:
        relationships_text = "\n".join(str(c) for c in _conflicts[:10])

    try:
        result = llm.generate_json(
            system_prompt="Bạn là biên tập viên kiểm tra tính nhất quán. Trả về JSON.",
            user_prompt=prompts.COHERENCE_CHECK.format(
                chapter_summaries=chapter_summaries,
                characters=characters_text,
                relationships=relationships_text or "Không có dữ liệu",
            ),
            temperature=0.2,
            model_tier="cheap",
        )

        issues = result.get("issues", [])
        enhanced.coherence_issues = [
            f"[{i.get('severity', 'warning')}] Ch{i.get('chapter', '?')}: {i.get('description', '')}"
            for i in issues
        ]

        logger.info(f"Kiểm tra nhất quán: phát hiện {len(issues)} vấn đề")
        return issues

    except Exception as e:
        logger.warning(f"Kiểm tra nhất quán thất bại: {e}")
        return []


def fix_coherence_issues(
    llm: LLMClient,
    enhanced: EnhancedStory,
    issues: list[dict],
    word_count: int = 2000,
) -> int:
    """Tự động sửa các vấn đề nhất quán nghiêm trọng. Trả về số chương đã sửa."""
    # Chỉ sửa vấn đề critical
    critical = [i for i in issues if i.get("severity") == "critical"]
    if not critical:
        return 0

    fixed = 0
    # Nhóm vấn đề theo chương
    by_chapter: dict[int, list[dict]] = {}
    for issue in critical:
        ch_num = issue.get("chapter", 0)
        by_chapter.setdefault(ch_num, []).append(issue)

    for ch_num, ch_issues in by_chapter.items():
        idx = ch_num - 1
        if idx < 0 or idx >= len(enhanced.chapters):
            continue

        chapter = enhanced.chapters[idx]
        issues_text = "\n".join(
            f"- [{i.get('type', 'unknown')}] {i.get('description', '')}"
            for i in ch_issues
        )
        fix_text = "\n".join(
            i.get("fix_suggestion", "") or i.get("description", "")
            for i in ch_issues
            if i.get("chapter") == ch_num
        )

        try:
            rewritten = llm.generate(
                system_prompt=(
                    "Bạn là nhà văn chuyên nghiệp. Sửa các vấn đề nhất quán. "
                    "BẮT BUỘC: Viết hoàn toàn bằng tiếng Việt."
                ),
                user_prompt=prompts.COHERENCE_FIX.format(
                    chapter_number=ch_num,
                    title=chapter.title,
                    content=chapter.content[:6000],
                    issues=issues_text,
                    fix_suggestion=fix_text,
                    word_count=word_count,
                ),
                max_tokens=8192,
            )

            enhanced.chapters[idx] = Chapter(
                chapter_number=ch_num,
                title=chapter.title,
                content=rewritten,
                word_count=count_words(rewritten),
                summary=chapter.summary,
            )
            fixed += 1
            logger.info(f"Đã sửa vấn đề nhất quán ở chương {ch_num}")

        except Exception as e:
            logger.warning(f"Không thể sửa vấn đề nhất quán ở chương {ch_num}: {e}")

    return fixed
