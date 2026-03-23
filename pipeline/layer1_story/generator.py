"""Layer 1: Tạo truyện từ đầu - Lấy cảm hứng từ create-story."""

import json
import logging
from typing import Optional, Generator

from models.schemas import (
    Character, WorldSetting, ChapterOutline, Chapter, StoryDraft,
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

        content = self.llm.generate(
            system_prompt=f"Bạn là tiểu thuyết gia tài năng viết truyện {genre} bằng tiếng Việt.",
            user_prompt=prompts.WRITE_CHAPTER.format(
                genre=genre, style=style, title=title,
                world=f"{world.name}: {world.description}",
                characters=chars_text,
                chapter_number=outline.chapter_number,
                chapter_title=outline.title,
                outline=outline_text,
                previous_summary=previous_summary or "Đây là chương đầu tiên.",
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

    def summarize_chapter(self, content: str) -> str:
        """Tóm tắt một chương để làm context cho chương tiếp."""
        return self.llm.generate(
            system_prompt="Bạn là trợ lý tóm tắt nội dung. Viết bằng tiếng Việt.",
            user_prompt=prompts.SUMMARIZE_CHAPTER.format(content=content[:3000]),
            max_tokens=500,
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

        # Viết từng chương
        previous_summary = ""
        for outline in outlines:
            _log(f"📖 Đang viết chương {outline.chapter_number}: {outline.title}...")
            chapter = self.write_chapter(
                title, genre, style, characters, world,
                outline, previous_summary, word_count,
            )
            draft.chapters.append(chapter)
            previous_summary = self.summarize_chapter(chapter.content)

        _log("✅ Layer 1 hoàn tất - Bản thảo truyện đã sẵn sàng!")
        return draft
