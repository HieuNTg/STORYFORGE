"""Tăng cường kịch tính cho truyện dựa trên kết quả mô phỏng."""

import logging
from models.schemas import (
    StoryDraft, SimulationResult, EnhancedStory, Chapter,
)
from services.llm_client import LLMClient
from services import prompts

logger = logging.getLogger(__name__)


class StoryEnhancer:
    """Viết lại truyện với tính kịch tích cao hơn."""

    def __init__(self):
        self.llm = LLMClient()

    def enhance_chapter(
        self,
        chapter: Chapter,
        sim_result: SimulationResult,
        word_count: int = 2000,
        total_chapters: int = 1,
    ) -> Chapter:
        """Tăng cường kịch tính cho một chương.

        Args:
            total_chapters: Tổng số chương trong truyện (để phân bổ sự kiện đều).
        """

        # Lọc sự kiện liên quan đến chương này
        relevant_events = [
            e for e in sim_result.events
            if str(chapter.chapter_number) in e.suggested_insertion
            or not e.suggested_insertion
        ]
        if not relevant_events:
            # Phân bổ đều sự kiện theo tổng số chương
            events_per_chapter = max(1, len(sim_result.events) // max(1, total_chapters))
            start = (chapter.chapter_number - 1) * events_per_chapter
            relevant_events = sim_result.events[start:start + events_per_chapter]

        events_text = "\n".join(
            f"- [{e.event_type}] {e.description} "
            f"(nhân vật: {', '.join(e.characters_involved)}, kịch tính: {e.drama_score:.1f})"
            for e in relevant_events[:5]
        ) or "Không có sự kiện cụ thể - tăng cường xung đột nội tâm."

        suggestions_text = "\n".join(
            f"- {s}" for s in sim_result.drama_suggestions[:5]
        ) or "Tăng cường miêu tả cảm xúc và xung đột."

        rel_text = "\n".join(
            f"- {r.character_a} ↔ {r.character_b}: {r.relation_type.value} "
            f"(xung đột: {r.tension:.1f})"
            for r in sim_result.updated_relationships[:10]
        )

        enhanced_content = self.llm.generate(
            system_prompt=(
                "Bạn là nhà văn tài năng chuyên viết truyện kịch tính. "
                "Viết hoàn toàn bằng tiếng Việt."
            ),
            user_prompt=prompts.ENHANCE_CHAPTER.format(
                original_chapter=chapter.content[:4000],
                drama_events=events_text,
                suggestions=suggestions_text,
                updated_relationships=rel_text,
                word_count=word_count,
            ),
            max_tokens=8192,
        )

        return Chapter(
            chapter_number=chapter.chapter_number,
            title=chapter.title,
            content=enhanced_content,
            word_count=len(enhanced_content.split()),
            summary=chapter.summary,
        )

    def enhance_story(
        self,
        draft: StoryDraft,
        sim_result: SimulationResult,
        word_count: int = 2000,
        progress_callback=None,
    ) -> EnhancedStory:
        """Tăng cường kịch tính cho toàn bộ truyện."""

        def _log(msg):
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)

        enhanced = EnhancedStory(
            title=draft.title,
            genre=draft.genre,
            enhancement_notes=[],
        )

        total_chapters = len(draft.chapters)
        for chapter in draft.chapters:
            _log(
                f"✨ Đang tăng cường kịch tính chương {chapter.chapter_number}: "
                f"{chapter.title}..."
            )
            enhanced_chapter = self.enhance_chapter(
                chapter, sim_result, word_count, total_chapters=total_chapters,
            )
            enhanced.chapters.append(enhanced_chapter)

        # Tính điểm kịch tính tổng thể
        if sim_result.events:
            enhanced.drama_score = sum(
                e.drama_score for e in sim_result.events
            ) / len(sim_result.events)
        enhanced.enhancement_notes = sim_result.drama_suggestions

        _log(
            f"✅ Layer 2 hoàn tất! Điểm kịch tính: {enhanced.drama_score:.2f}"
        )
        return enhanced
