"""L3 Sensory Polish — lightweight post-L2 prose enhancement.

Adds sensory details (sight, sound, smell, touch, taste) to enhance immersion.
Optional final pass after drama enhancement.
"""

import logging
from models.schemas import Chapter, EnhancedStory, count_words
from services.llm_client import LLMClient

logger = logging.getLogger(__name__)

_SENSORY_PROMPT = """{user_story_idea_header}Thêm chi tiết giác quan vào đoạn văn sau để tăng sự sống động.
Giữ nguyên cốt truyện, nhân vật, và giọng văn. Chỉ thêm:
- Thị giác: màu sắc, ánh sáng, bóng tối
- Thính giác: âm thanh, tiếng động, im lặng
- Khứu giác: mùi hương, mùi vị
- Xúc giác: nhiệt độ, kết cấu, cảm giác
- Vị giác: (nếu phù hợp ngữ cảnh)

Quy tắc:
- Không thay đổi sự kiện hoặc hội thoại
- Thêm TỐI ĐA 2-3 chi tiết giác quan mỗi đoạn
- Giữ độ dài tương đương (±10%)
- Viết hoàn toàn bằng tiếng Việt
- PHẢI giữ nguyên tên riêng / địa danh / gimmick từ [Ý TƯỞNG GỐC] ở đầu prompt — không Việt hoá, không dịch, không thay thế

Nội dung:
{content}

Viết lại với chi tiết giác quan (không giải thích):"""


class SensoryPolisher:
    """Lightweight sensory enhancement for prose."""

    LAYER = 3

    def __init__(self):
        self.llm = LLMClient()
        self._layer_model = self.llm.model_for_layer(self.LAYER)

    def polish_chapter(
        self,
        chapter: Chapter,
        max_tokens: int = 8192,
        idea_header: str = "",
    ) -> Chapter:
        """Add sensory details to a chapter."""
        try:
            polished = self.llm.generate(
                system_prompt=(
                    "Bạn là nhà văn chuyên thêm chi tiết giác quan. "
                    "BẮT BUỘC: Viết hoàn toàn bằng tiếng Việt."
                ),
                user_prompt=_SENSORY_PROMPT.format(
                    user_story_idea_header=idea_header,
                    content=chapter.content[:12000],
                ),
                max_tokens=max_tokens,
                model=self._layer_model,
            )
            return Chapter(
                chapter_number=chapter.chapter_number,
                title=chapter.title,
                content=polished,
                word_count=count_words(polished),
                summary=chapter.summary,
            )
        except Exception as e:
            logger.warning(f"Sensory polish ch{chapter.chapter_number} failed: {e}")
            return chapter

    def polish_story(
        self,
        enhanced: EnhancedStory,
        progress_callback=None,
        idea: str = "",
        idea_summary: str = "",
    ) -> EnhancedStory:
        """Polish all chapters in an enhanced story."""
        from services.text_utils import build_idea_header
        idea_header = build_idea_header(idea, idea_summary) if idea else ""

        polished_chapters = []
        for i, chapter in enumerate(enhanced.chapters):
            if progress_callback:
                progress_callback(f"[L3] Polishing chapter {chapter.chapter_number}...")
            polished = self.polish_chapter(chapter, idea_header=idea_header)
            polished_chapters.append(polished)
        enhanced.chapters = polished_chapters
        return enhanced


def apply_sensory_polish(
    enhanced: EnhancedStory,
    enabled: bool = False,
    progress_callback=None,
    draft=None,
) -> EnhancedStory:
    """Apply sensory polish if enabled. No-op if disabled.

    `draft` (optional) supplies the author's original_idea so polish doesn't
    drift proper nouns / gimmicks back to genre default.
    """
    if not enabled:
        return enhanced
    try:
        polisher = SensoryPolisher()
        _idea = getattr(draft, "original_idea", "") or "" if draft is not None else ""
        _idea_sum = getattr(draft, "idea_summary_for_chapters", "") or "" if draft is not None else ""
        return polisher.polish_story(
            enhanced, progress_callback,
            idea=_idea, idea_summary=_idea_sum,
        )
    except Exception as e:
        logger.warning(f"Sensory polish failed (non-fatal): {e}")
        return enhanced
