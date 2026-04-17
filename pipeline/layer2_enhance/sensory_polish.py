"""L3 Sensory Polish — lightweight post-L2 prose enhancement.

Adds sensory details (sight, sound, smell, touch, taste) to enhance immersion.
Optional final pass after drama enhancement.
"""

import logging
from typing import Optional
from models.schemas import Chapter, EnhancedStory, count_words
from services.llm_client import LLMClient

logger = logging.getLogger(__name__)

_SENSORY_PROMPT = """Thêm chi tiết giác quan vào đoạn văn sau để tăng sự sống động.
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
    ) -> Chapter:
        """Add sensory details to a chapter."""
        try:
            polished = self.llm.generate(
                system_prompt=(
                    "Bạn là nhà văn chuyên thêm chi tiết giác quan. "
                    "BẮT BUỘC: Viết hoàn toàn bằng tiếng Việt."
                ),
                user_prompt=_SENSORY_PROMPT.format(content=chapter.content[:12000]),
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
    ) -> EnhancedStory:
        """Polish all chapters in an enhanced story."""
        polished_chapters = []
        for i, chapter in enumerate(enhanced.chapters):
            if progress_callback:
                progress_callback(f"[L3] Polishing chapter {chapter.chapter_number}...")
            polished = self.polish_chapter(chapter)
            polished_chapters.append(polished)
        enhanced.chapters = polished_chapters
        return enhanced


def apply_sensory_polish(
    enhanced: EnhancedStory,
    enabled: bool = False,
    progress_callback=None,
) -> EnhancedStory:
    """Apply sensory polish if enabled. No-op if disabled."""
    if not enabled:
        return enhanced
    try:
        polisher = SensoryPolisher()
        return polisher.polish_story(enhanced, progress_callback)
    except Exception as e:
        logger.warning(f"Sensory polish failed (non-fatal): {e}")
        return enhanced
