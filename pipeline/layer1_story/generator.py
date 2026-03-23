"""Layer 1: Tạo truyện từ đầu - Lấy cảm hứng từ create-story."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Generator

from models.schemas import (
    Character, WorldSetting, ChapterOutline, Chapter, StoryDraft,
    CharacterState, PlotEvent, StoryContext,
)
from services.llm_client import LLMClient
from services import prompts
from config import ConfigManager

logger = logging.getLogger(__name__)


class StoryGenerator:
    """Tạo truyện hoàn chỉnh từ ý tưởng ban đầu."""

    def __init__(self):
        self.llm = LLMClient()
        self.config = ConfigManager()

    def suggest_titles(self, genre: str, requirements: str = "") -> list[str]:
        """Đề xuất tiêu đề truyện."""
        result = self.llm.generate_json(
            system_prompt="Bạn là nhà văn sáng tạo. Trả về JSON.",
            user_prompt=prompts.SUGGEST_TITLE.format(
                genre=genre, requirements=requirements
            ),
        )
        return result.get("titles", [])

    def generate_characters(
        self, title: str, genre: str, idea: str, num_characters: int = 5
    ) -> list[Character]:
        """Tạo danh sách nhân vật."""
        result = self.llm.generate_json(
            system_prompt="Bạn là nhà văn chuyên xây dựng nhân vật. Trả về JSON.",
            user_prompt=prompts.GENERATE_CHARACTERS.format(
                genre=genre, title=title, idea=idea,
                num_characters=num_characters,
            ),
        )
        return [Character(**c) for c in result.get("characters", [])]

    def generate_world(
        self, title: str, genre: str, characters: list[Character]
    ) -> WorldSetting:
        """Tạo bối cảnh thế giới."""
        chars_text = "\n".join(
            f"- {c.name} ({c.role}): {c.personality}" for c in characters
        )
        result = self.llm.generate_json(
            system_prompt="Bạn là kiến trúc sư thế giới. Trả về JSON.",
            user_prompt=prompts.GENERATE_WORLD.format(
                genre=genre, title=title, characters=chars_text,
            ),
        )
        return WorldSetting(**result)

    def generate_outline(
        self,
        title: str,
        genre: str,
        characters: list[Character],
        world: WorldSetting,
        idea: str,
        num_chapters: int = 10,
    ) -> tuple[str, list[ChapterOutline]]:
        """Tạo dàn ý toàn bộ truyện. Trả về (synopsis, outlines)."""
        chars_text = "\n".join(
            f"- {c.name} ({c.role}): {c.personality}, Động lực: {c.motivation}"
            for c in characters
        )
        result = self.llm.generate_json(
            system_prompt="Bạn là biên kịch tài năng. Trả về JSON.",
            user_prompt=prompts.GENERATE_OUTLINE.format(
                genre=genre, title=title, characters=chars_text,
                world=f"{world.name}: {world.description}",
                idea=idea, num_chapters=num_chapters,
            ),
            temperature=0.9,
        )
        synopsis = result.get("synopsis", "")
        outlines = [ChapterOutline(**o) for o in result.get("outlines", [])]
        return synopsis, outlines

    def _format_context(self, context: StoryContext) -> str:
        """Format StoryContext thành chuỗi cho prompt."""
        if not context or (not context.recent_summaries and not context.character_states):
            return "Đây là chương đầu tiên."

        parts = []
        if context.recent_summaries:
            parts.append("## Bối cảnh các chương trước:\n" + "\n---\n".join(context.recent_summaries))
        if context.character_states:
            states_text = "\n".join(
                f"- {s.name}: tâm trạng={s.mood}, vị trí={s.arc_position}, "
                f"hành động cuối={s.last_action}"
                for s in context.character_states
            )
            parts.append(f"## Trạng thái nhân vật hiện tại:\n{states_text}")
        if context.plot_events:
            events_text = "\n".join(
                f"- Ch.{e.chapter_number}: {e.event}" for e in context.plot_events[-10:]
            )
            parts.append(f"## Sự kiện quan trọng đã xảy ra:\n{events_text}")

        return "\n\n".join(parts)

    def write_chapter(
        self,
        title: str,
        genre: str,
        style: str,
        characters: list[Character],
        world: WorldSetting,
        outline: ChapterOutline,
        previous_summary: str = "",
        word_count: int = 2000,
        context: Optional[StoryContext] = None,
    ) -> Chapter:
        """Viết một chương truyện."""
        chars_text = "\n".join(
            f"- {c.name} ({c.role}): {c.personality}\n  Tiểu sử: {c.background}"
            for c in characters
        )
        outline_text = (
            f"Tóm tắt: {outline.summary}\n"
            f"Sự kiện chính: {', '.join(outline.key_events)}\n"
            f"Cảm xúc: {outline.emotional_arc}"
        )
        # Use StoryContext if provided, else fall back to previous_summary
        context_text = self._format_context(context) if context else (previous_summary or "Đây là chương đầu tiên.")

        content = self.llm.generate(
            system_prompt=f"Bạn là tiểu thuyết gia tài năng viết truyện {genre} bằng tiếng Việt.",
            user_prompt=prompts.WRITE_CHAPTER.format(
                genre=genre, style=style, title=title,
                world=f"{world.name}: {world.description}",
                characters=chars_text,
                chapter_number=outline.chapter_number,
                chapter_title=outline.title,
                outline=outline_text,
                previous_summary=context_text,
                word_count=word_count,
            ),
            max_tokens=8192,
        )

        return Chapter(
            chapter_number=outline.chapter_number,
            title=outline.title,
            content=content,
            word_count=len(content.split()),
        )

    @staticmethod
    def _excerpt(content: str, max_chars: int = 4000) -> str:
        """Extract beginning + end of content for extraction prompts."""
        if len(content) <= max_chars:
            return content
        head = max_chars * 2 // 3
        tail = max_chars - head
        return content[:head] + "\n...\n" + content[-tail:]

    def extract_character_states(
        self, content: str, characters: list[Character]
    ) -> list[CharacterState]:
        """Trích xuất trạng thái nhân vật từ nội dung chương. Low temp, cheap call."""
        chars_text = ", ".join(c.name for c in characters)
        result = self.llm.generate_json(
            system_prompt="Trích xuất trạng thái nhân vật. Trả về JSON.",
            user_prompt=prompts.EXTRACT_CHARACTER_STATE.format(
                content=self._excerpt(content), characters=chars_text,
            ),
            temperature=0.3,
            max_tokens=1000,
            model_tier="cheap",
        )
        states = []
        for s in result.get("character_states", []):
            try:
                states.append(CharacterState(**s))
            except Exception as e:
                logger.debug(f"Skipping invalid character state: {e}")
                continue
        return states

    def extract_plot_events(
        self, content: str, chapter_number: int
    ) -> list[PlotEvent]:
        """Trích xuất sự kiện quan trọng từ nội dung chương."""
        result = self.llm.generate_json(
            system_prompt="Trích xuất sự kiện cốt truyện. Trả về JSON.",
            user_prompt=prompts.EXTRACT_PLOT_EVENTS.format(
                content=self._excerpt(content), chapter_number=chapter_number,
            ),
            temperature=0.3,
            max_tokens=1000,
            model_tier="cheap",
        )
        events = []
        for e in result.get("events", []):
            try:
                events.append(PlotEvent(chapter_number=chapter_number, **e))
            except Exception as ex:
                logger.debug(f"Skipping invalid plot event: {ex}")
                continue
        return events

    def summarize_chapter(self, content: str) -> str:
        """Tóm tắt một chương để làm context cho chương tiếp."""
        return self.llm.generate(
            system_prompt="Bạn là trợ lý tóm tắt nội dung. Viết bằng tiếng Việt.",
            user_prompt=prompts.SUMMARIZE_CHAPTER.format(content=content[:3000]),
            temperature=0.3,
            max_tokens=500,
            model_tier="cheap",
        )

    def generate_full_story(
        self,
        title: str,
        genre: str,
        idea: str,
        style: str = "Miêu tả chi tiết",
        num_chapters: int = 10,
        num_characters: int = 5,
        word_count: int = 2000,
        progress_callback=None,
    ) -> StoryDraft:
        """Tạo toàn bộ truyện từ đầu đến cuối."""
        context_window = self.config.pipeline.context_window_chapters

        def _log(msg):
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)

        _log(f"🖊️ Đang tạo nhân vật cho '{title}'...")
        characters = self.generate_characters(title, genre, idea, num_characters)

        _log("🌍 Đang xây dựng bối cảnh thế giới...")
        world = self.generate_world(title, genre, characters)

        _log(f"📋 Đang tạo dàn ý {num_chapters} chương...")
        synopsis, outlines = self.generate_outline(
            title, genre, characters, world, idea, num_chapters
        )

        draft = StoryDraft(
            title=title,
            genre=genre,
            synopsis=synopsis,
            characters=characters,
            world=world,
            outlines=outlines,
        )

        # Rolling context for chapter-to-chapter coherence
        story_context = StoryContext(total_chapters=len(outlines))

        with ThreadPoolExecutor(max_workers=3) as executor:
            for outline in outlines:
                story_context.current_chapter = outline.chapter_number

                _log(f"📖 Đang viết chương {outline.chapter_number}: {outline.title}...")
                chapter = self.write_chapter(
                    title, genre, style, characters, world,
                    outline, word_count=word_count, context=story_context,
                )
                draft.chapters.append(chapter)

                # Parallel extraction: summary + character states + plot events
                _log(f"🔍 Đang trích xuất context chương {outline.chapter_number}...")
                summary_f = executor.submit(self.summarize_chapter, chapter.content)
                states_f = executor.submit(
                    self.extract_character_states, chapter.content, characters
                )
                events_f = executor.submit(
                    self.extract_plot_events, chapter.content, outline.chapter_number
                )

                # Collect results with fallbacks
                try:
                    summary = summary_f.result()
                except Exception as e:
                    logger.warning(f"Summary extraction failed: {e}")
                    summary = ""

                try:
                    new_states = states_f.result()
                except Exception as e:
                    logger.warning(f"Character state extraction failed: {e}")
                    new_states = []

                try:
                    new_events = events_f.result()
                except Exception as e:
                    logger.warning(f"Plot event extraction failed: {e}")
                    new_events = []

                # Update rolling context
                chapter.summary = summary
                story_context.recent_summaries.append(summary)
                # Keep only last N summaries
                story_context.recent_summaries = story_context.recent_summaries[-context_window:]

                # Merge character states (latest wins per character name)
                if new_states:
                    existing = {s.name: s for s in story_context.character_states}
                    for s in new_states:
                        existing[s.name] = s
                    story_context.character_states = list(existing.values())

                story_context.plot_events.extend(new_events)
                # Cap to last 50 events in context to prevent unbounded growth
                story_context.plot_events = story_context.plot_events[-50:]

        # Store final states in draft for Layer 2
        draft.character_states = list(story_context.character_states)
        draft.plot_events = list(story_context.plot_events)

        _log("✅ Layer 1 hoàn tất - Bản thảo truyện đã sẵn sàng!")
        return draft
