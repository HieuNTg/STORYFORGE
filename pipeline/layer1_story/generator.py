"""Layer 1: Tạo truyện từ đầu - Lấy cảm hứng từ create-story."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Generator

from models.schemas import (
    Character, WorldSetting, ChapterOutline, Chapter, StoryDraft,
    CharacterState, PlotEvent, StoryContext, count_words,
)
from services.llm_client import LLMClient
from services import prompts
from services.input_sanitizer import sanitize_story_input
from services.adaptive_prompts import build_adaptive_write_prompt
from config import ConfigManager
from pipeline.layer1_story.story_bible_manager import StoryBibleManager

logger = logging.getLogger(__name__)

# Lazy import — only instantiated when rag_enabled=True
_rag_kb = None


def _get_rag_kb(persist_dir: str):
    """Return a shared RAGKnowledgeBase instance (lazy init)."""
    global _rag_kb
    if _rag_kb is None:
        try:
            from services.rag_knowledge_base import RAGKnowledgeBase
            _rag_kb = RAGKnowledgeBase(persist_dir=persist_dir)
        except Exception as e:
            logger.warning(f"RAG init failed: {e}")
            return None
    return _rag_kb


class StoryGenerator:
    """Tạo truyện hoàn chỉnh từ ý tưởng ban đầu."""

    def __init__(self):
        self.llm = LLMClient()
        self.config = ConfigManager()
        self.bible_manager = StoryBibleManager()
        self._long_ctx_client = None

    @property
    def long_context_client(self):
        if self._long_ctx_client is None:
            from services.long_context_client import LongContextClient
            self._long_ctx_client = LongContextClient()
        return self._long_ctx_client

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
        world_prompt = prompts.GENERATE_WORLD.format(
            genre=genre, title=title, characters=chars_text,
        )
        # Prepend RAG context if enabled
        if self.config.pipeline.rag_enabled:
            rag_kb = _get_rag_kb(self.config.pipeline.rag_persist_dir)
            if rag_kb and rag_kb.is_available:
                rag_docs = rag_kb.query(f"world setting {genre} {title}", n_results=3)
                if rag_docs:
                    rag_section = prompts.RAG_CONTEXT_SECTION.format(
                        rag_context="\n---\n".join(rag_docs)
                    )
                    world_prompt = rag_section + world_prompt

        result = self.llm.generate_json(
            system_prompt="Bạn là kiến trúc sư thế giới. Trả về JSON.",
            user_prompt=world_prompt,
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

    def _format_context(
        self,
        context: StoryContext,
        bible_context: str = "",
        full_chapter_texts: Optional[list[str]] = None,
    ) -> str:
        """Format StoryContext thành chuỗi cho prompt.

        Nếu full_chapter_texts được cung cấp (long-context mode), format toàn bộ
        nội dung chương dưới dạng numbered sections kèm character states/plot events.
        Nếu bible_context được cung cấp (từ StoryBible), dùng nó thay vì rolling summaries.
        """
        # Long-context mode: include full chapter texts
        if full_chapter_texts:
            parts = []
            parts.append("## Toàn bộ nội dung các chương trước:")
            for i, text in enumerate(full_chapter_texts, start=1):
                parts.append(f"### Chương {i}:\n{text}")
            # Still include character states and plot events for reference
            if context and context.character_states:
                states_text = "\n".join(
                    f"- {s.name}: tâm trạng={s.mood}, vị trí={s.arc_position}, "
                    f"hành động cuối={s.last_action}"
                    for s in context.character_states
                )
                parts.append(f"## Trạng thái nhân vật hiện tại:\n{states_text}")
            if context and context.plot_events:
                events_text = "\n".join(
                    f"- Ch.{e.chapter_number}: {e.event}" for e in context.plot_events[-10:]
                )
                parts.append(f"## Sự kiện quan trọng đã xảy ra:\n{events_text}")
            return "\n\n".join(parts)

        if not context or (not context.recent_summaries and not context.character_states):
            return bible_context or "Đây là chương đầu tiên."

        # Khi có bible context, dùng nó — đã bao gồm summaries và char states
        if bible_context:
            return bible_context

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

    def _build_chapter_prompt(
        self, title, genre, style, characters, world, outline,
        word_count, context=None, previous_summary="", bible_context: str = "",
        full_chapter_texts: Optional[list[str]] = None,
    ) -> tuple[str, str]:
        """Build system/user prompts for chapter writing. Returns (system_prompt, user_prompt)."""
        chars_text = "\n".join(
            f"- {c.name} ({c.role}): {c.personality}\n  Tiểu sử: {c.background}"
            for c in characters
        )
        outline_text = (
            f"Tóm tắt: {outline.summary}\n"
            f"Sự kiện chính: {', '.join(outline.key_events)}\n"
            f"Cảm xúc: {outline.emotional_arc}"
        )
        context_text = (
            self._format_context(context, bible_context, full_chapter_texts)
            if context
            else (bible_context or previous_summary or "Đây là chương đầu tiên.")
        )

        # Append RAG context if enabled
        if self.config.pipeline.rag_enabled:
            rag_kb = _get_rag_kb(self.config.pipeline.rag_persist_dir)
            if rag_kb and rag_kb.is_available:
                query_text = f"chapter {outline.chapter_number} {outline.summary}"
                rag_docs = rag_kb.query(query_text, n_results=3)
                if rag_docs:
                    rag_section = prompts.RAG_CONTEXT_SECTION.format(
                        rag_context="\n---\n".join(rag_docs)
                    )
                    context_text = context_text + "\n\n" + rag_section

        sys_prompt = f"Bạn là tiểu thuyết gia tài năng viết truyện {genre} bằng tiếng Việt."
        user_prompt = prompts.WRITE_CHAPTER.format(
            genre=genre, style=style, title=title,
            world=f"{world.name}: {world.description}",
            characters=chars_text,
            chapter_number=outline.chapter_number,
            chapter_title=outline.title,
            outline=outline_text,
            previous_summary=context_text,
            word_count=word_count,
        )
        user_prompt = build_adaptive_write_prompt(user_prompt, genre)
        return sys_prompt, user_prompt

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
        sys_prompt, user_prompt = self._build_chapter_prompt(
            title, genre, style, characters, world, outline,
            word_count, context, previous_summary,
        )
        content = self.llm.generate(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            max_tokens=8192,
        )
        return Chapter(
            chapter_number=outline.chapter_number,
            title=outline.title,
            content=content,
            word_count=count_words(content),
        )

    def write_chapter_stream(
        self,
        title: str,
        genre: str,
        style: str,
        characters: list[Character],
        world: WorldSetting,
        outline: ChapterOutline,
        word_count: int = 2000,
        context: Optional[StoryContext] = None,
        stream_callback=None,
    ) -> Chapter:
        """Viết chương với streaming. Gọi stream_callback(partial_text) mỗi chunk."""
        sys_prompt, user_prompt = self._build_chapter_prompt(
            title, genre, style, characters, world, outline, word_count, context,
        )

        full_content = ""
        try:
            for token in self.llm.generate_stream(
                system_prompt=sys_prompt,
                user_prompt=user_prompt,
                max_tokens=8192,
            ):
                full_content += token
                if stream_callback:
                    stream_callback(full_content)
        except Exception as e:
            # Fallback: discard partial, use non-streaming
            logger.warning(f"Stream failed, falling back to generate: {e}")
            return self.write_chapter(
                title, genre, style, characters, world,
                outline, word_count=word_count, context=context,
            )

        return Chapter(
            chapter_number=outline.chapter_number,
            title=outline.title,
            content=full_content,
            word_count=count_words(full_content),
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
        stream_callback=None,
    ) -> StoryDraft:
        """Tạo toàn bộ truyện từ đầu đến cuối."""
        context_window = self.config.pipeline.context_window_chapters

        def _log(msg):
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)

        # Soft injection defense — log threats but don't block
        _san = sanitize_story_input(title=title, idea=idea, genre=genre)
        if not _san.is_safe:
            logger.warning(f"Injection threats in story input: {_san.threats_found}")

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

        # Khởi tạo Story Bible nếu được bật
        bible_enabled = self.config.pipeline.story_bible_enabled
        if bible_enabled:
            draft.story_bible = self.bible_manager.initialize(
                draft, arc_size=self.config.pipeline.arc_size
            )

        # Long-context tracking: accumulate full chapter texts
        all_chapter_texts = []

        with ThreadPoolExecutor(max_workers=3) as executor:
            for outline in outlines:
                story_context.current_chapter = outline.chapter_number

                # Tạo bible context cho chương này (nếu có bible)
                bible_ctx = ""
                if bible_enabled and draft.story_bible:
                    bible_ctx = self.bible_manager.get_context_for_chapter(
                        draft.story_bible,
                        outline.chapter_number,
                        recent_summaries=list(story_context.recent_summaries),
                        character_states=list(story_context.character_states),
                    )

                _log(f"📖 Đang viết chương {outline.chapter_number}: {outline.title}...")
                if stream_callback:
                    chapter = self.write_chapter_stream(
                        title, genre, style, characters, world,
                        outline, word_count=word_count, context=story_context,
                        stream_callback=stream_callback,
                    )
                else:
                    # Decide whether to use long-context mode (skip for first chapter)
                    use_lc = False
                    if (
                        all_chapter_texts
                        and self.config.pipeline.use_long_context
                        and self.long_context_client.is_configured
                    ):
                        from services.token_counter import fits_in_context
                        if fits_in_context(all_chapter_texts, self.long_context_client.max_context):
                            use_lc = True
                        else:
                            logger.info(
                                f"Chapter {outline.chapter_number}: long-context skipped "
                                f"(texts exceed context window), falling back to rolling context"
                            )

                    sys_prompt, user_prompt = self._build_chapter_prompt(
                        title, genre, style, characters, world, outline,
                        word_count, story_context, bible_context=bible_ctx,
                        full_chapter_texts=all_chapter_texts if use_lc else None,
                    )
                    if use_lc:
                        content = self.long_context_client.generate(
                            system_prompt=sys_prompt,
                            user_prompt=user_prompt,
                            max_tokens=8192,
                        )
                    else:
                        content = self.llm.generate(
                            system_prompt=sys_prompt,
                            user_prompt=user_prompt,
                            max_tokens=8192,
                        )
                    chapter = Chapter(
                        chapter_number=outline.chapter_number,
                        title=outline.title,
                        content=content,
                        word_count=count_words(content),
                    )
                # Optional self-review (opt-in via config.pipeline.enable_self_review)
                if self.config.pipeline.enable_self_review:
                    if not hasattr(self, '_self_reviewer'):
                        from services.self_review import SelfReviewer
                        self._self_reviewer = SelfReviewer(
                            threshold=self.config.pipeline.self_review_threshold
                        )
                    reviewer = self._self_reviewer
                    revised_content, review_scores = reviewer.review_and_revise(
                        content=chapter.content,
                        chapter_number=outline.chapter_number,
                        title=outline.title,
                        genre=genre,
                        word_count=word_count,
                    )
                    if revised_content != chapter.content:
                        if progress_callback:
                            progress_callback(
                                f"Chuong {outline.chapter_number} da duoc cai thien "
                                f"(score: {review_scores['overall']:.1f})"
                            )
                        chapter.content = revised_content
                        chapter.word_count = count_words(revised_content)

                draft.chapters.append(chapter)
                all_chapter_texts.append(chapter.content)

                # Parallel extraction: summary + character states + plot events
                _log(f"🔍 Đang trích xuất context chương {outline.chapter_number}...")
                summary_f = executor.submit(self.summarize_chapter, chapter.content)
                states_f = executor.submit(
                    self.extract_character_states, chapter.content, characters
                )
                events_f = executor.submit(
                    self.extract_plot_events, chapter.content, outline.chapter_number
                )

                # Collect results with timeout (120s) to prevent pipeline hang
                _EXTRACTION_TIMEOUT = 120
                try:
                    summary = summary_f.result(timeout=_EXTRACTION_TIMEOUT)
                except Exception as e:
                    logger.warning(f"Summary extraction failed: {e}")
                    summary = ""
                    summary_f.cancel()

                try:
                    new_states = states_f.result(timeout=_EXTRACTION_TIMEOUT)
                except Exception as e:
                    logger.warning(f"Character state extraction failed: {e}")
                    new_states = []
                    states_f.cancel()

                try:
                    new_events = events_f.result(timeout=_EXTRACTION_TIMEOUT)
                except Exception as e:
                    logger.warning(f"Plot event extraction failed: {e}")
                    new_events = []
                    events_f.cancel()

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
                # Smart pruning: keep recent + high-impact events (cap at 50)
                if len(story_context.plot_events) > 50:
                    events = story_context.plot_events
                    recent = events[-30:]
                    # From older events, keep top 20 by importance (longer event text = more detail)
                    older = sorted(events[:-30], key=lambda e: len(e.event), reverse=True)[:20]
                    story_context.plot_events = older + recent

                # Cập nhật Story Bible
                if bible_enabled and draft.story_bible:
                    self.bible_manager.update_after_chapter(
                        draft.story_bible, chapter,
                        list(story_context.character_states), new_events,
                    )

        # Store final states in draft for Layer 2
        draft.character_states = list(story_context.character_states)
        draft.plot_events = list(story_context.plot_events)

        _log("✅ Layer 1 hoàn tất - Bản thảo truyện đã sẵn sàng!")
        return draft

    def rebuild_context(self, draft: StoryDraft) -> StoryContext:
        """Rebuild StoryContext from existing StoryDraft chapters."""
        context_window = self.config.pipeline.context_window_chapters
        context = StoryContext(
            total_chapters=len(draft.chapters),
            current_chapter=len(draft.chapters),
        )
        # Use chapter summaries as recent_summaries
        for ch in draft.chapters[-context_window:]:
            if ch.summary:
                context.recent_summaries.append(ch.summary)
            else:
                logger.warning(f"Chapter {ch.chapter_number} has no summary for context rebuild")
        # Use stored character states and plot events
        context.character_states = list(draft.character_states)
        context.plot_events = list(draft.plot_events[-50:])
        return context

    def continue_story(
        self,
        draft: StoryDraft,
        additional_chapters: int = 5,
        word_count: int = 2000,
        style: str = "",
        progress_callback=None,
        stream_callback=None,
    ) -> StoryDraft:
        """Continue writing from existing StoryDraft by adding more chapters."""
        context_window = self.config.pipeline.context_window_chapters
        effective_style = style or self.config.pipeline.writing_style

        def _log(msg):
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)

        start_chapter = len(draft.chapters) + 1
        _log(f"📋 Generating outlines for chapters {start_chapter}-{start_chapter + additional_chapters - 1}...")

        # Build context strings for outline generation
        chars_text = "\n".join(
            f"- {c.name} ({c.role}): {c.personality}, Động lực: {c.motivation}"
            for c in draft.characters
        )
        existing_outlines_text = "\n".join(
            f"Ch.{o.chapter_number}: {o.title} — {o.summary}"
            for o in draft.outlines
        )
        states_text = "\n".join(
            f"- {s.name}: mood={s.mood}, arc={s.arc_position}, last={s.last_action}"
            for s in draft.character_states
        ) or "N/A"
        events_text = "\n".join(
            f"- Ch.{e.chapter_number}: {e.event}"
            for e in draft.plot_events[-20:]
        ) or "N/A"

        world_text = f"{draft.world.name}: {draft.world.description}" if draft.world else "N/A"

        result = self.llm.generate_json(
            system_prompt="Bạn là biên kịch tài năng. Trả về JSON.",
            user_prompt=prompts.CONTINUE_OUTLINE.format(
                genre=draft.genre, title=draft.title,
                characters=chars_text, world=world_text,
                existing_chapters=len(draft.chapters),
                synopsis=draft.synopsis,
                existing_outlines=existing_outlines_text,
                character_states=states_text,
                plot_events=events_text,
                additional_chapters=additional_chapters,
                start_chapter=start_chapter,
            ),
            temperature=0.9,
        )
        new_outlines = [ChapterOutline(**o) for o in result.get("outlines", [])]
        if not new_outlines:
            _log("⚠️ No outlines generated. Aborting continuation.")
            return draft

        draft.outlines.extend(new_outlines)

        # Rebuild context from existing chapters
        story_context = self.rebuild_context(draft)

        # Collect existing chapter texts for potential long-context usage
        all_chapter_texts = [ch.content for ch in draft.chapters if ch.content]

        final_total = len(draft.chapters) + len(new_outlines)
        with ThreadPoolExecutor(max_workers=3) as executor:
            for outline in new_outlines:
                story_context.current_chapter = outline.chapter_number
                story_context.total_chapters = final_total

                _log(f"📖 Writing chapter {outline.chapter_number}: {outline.title}...")
                if stream_callback:
                    chapter = self.write_chapter_stream(
                        draft.title, draft.genre, effective_style,
                        draft.characters, draft.world, outline,
                        word_count=word_count, context=story_context,
                        stream_callback=stream_callback,
                    )
                else:
                    # Decide whether to use long-context mode
                    use_lc = False
                    if (
                        all_chapter_texts
                        and self.config.pipeline.use_long_context
                        and self.long_context_client.is_configured
                    ):
                        from services.token_counter import fits_in_context
                        if fits_in_context(all_chapter_texts, self.long_context_client.max_context):
                            use_lc = True
                        else:
                            logger.info(
                                f"Chapter {outline.chapter_number}: long-context skipped "
                                f"(texts exceed context window), falling back to rolling context"
                            )

                    if use_lc:
                        sys_prompt, user_prompt = self._build_chapter_prompt(
                            draft.title, draft.genre, effective_style,
                            draft.characters, draft.world, outline,
                            word_count, story_context,
                            full_chapter_texts=all_chapter_texts,
                        )
                        chapter_content = self.long_context_client.generate(
                            system_prompt=sys_prompt,
                            user_prompt=user_prompt,
                            max_tokens=8192,
                        )
                        chapter = Chapter(
                            chapter_number=outline.chapter_number,
                            title=outline.title,
                            content=chapter_content,
                            word_count=count_words(chapter_content),
                        )
                    else:
                        chapter = self.write_chapter(
                            draft.title, draft.genre, effective_style,
                            draft.characters, draft.world, outline,
                            word_count=word_count, context=story_context,
                        )
                # Optional self-review for continued chapters
                if self.config.pipeline.enable_self_review:
                    if not hasattr(self, '_self_reviewer'):
                        from services.self_review import SelfReviewer
                        self._self_reviewer = SelfReviewer(
                            threshold=self.config.pipeline.self_review_threshold
                        )
                    revised, scores = self._self_reviewer.review_and_revise(
                        content=chapter.content,
                        chapter_number=outline.chapter_number,
                        title=outline.title,
                        genre=draft.genre,
                        word_count=word_count,
                    )
                    if revised != chapter.content:
                        _log(f"Chuong {outline.chapter_number} da duoc cai thien "
                             f"(score: {scores['overall']:.1f})")
                        chapter.content = revised
                        chapter.word_count = count_words(revised)

                draft.chapters.append(chapter)
                all_chapter_texts.append(chapter.content)

                # Parallel extraction
                _log(f"🔍 Extracting context for chapter {outline.chapter_number}...")
                summary_f = executor.submit(self.summarize_chapter, chapter.content)
                states_f = executor.submit(
                    self.extract_character_states, chapter.content, draft.characters
                )
                events_f = executor.submit(
                    self.extract_plot_events, chapter.content, outline.chapter_number
                )

                _EXTRACTION_TIMEOUT = 120
                try:
                    summary = summary_f.result(timeout=_EXTRACTION_TIMEOUT)
                except Exception:
                    summary = ""
                    summary_f.cancel()
                try:
                    new_states = states_f.result(timeout=_EXTRACTION_TIMEOUT)
                except Exception:
                    new_states = []
                    states_f.cancel()
                try:
                    new_events = events_f.result(timeout=_EXTRACTION_TIMEOUT)
                except Exception:
                    new_events = []
                    events_f.cancel()

                chapter.summary = summary
                story_context.recent_summaries.append(summary)
                story_context.recent_summaries = story_context.recent_summaries[-context_window:]

                if new_states:
                    existing = {s.name: s for s in story_context.character_states}
                    for s in new_states:
                        existing[s.name] = s
                    story_context.character_states = list(existing.values())

                story_context.plot_events.extend(new_events)
                # Smart pruning: keep recent + high-drama events
                if len(story_context.plot_events) > 50:
                    events = story_context.plot_events
                    recent = events[-30:]
                    older = sorted(events[:-30], key=lambda e: len(e.description), reverse=True)[:20]
                    story_context.plot_events = older + recent

        draft.character_states = list(story_context.character_states)
        draft.plot_events = list(story_context.plot_events)

        _log(f"✅ Continuation complete — {len(new_outlines)} chapters added!")
        return draft

    @staticmethod
    def remove_chapters(draft: StoryDraft, from_chapter: int) -> StoryDraft:
        """Remove chapters from `from_chapter` onward. Returns modified draft."""
        draft.chapters = [ch for ch in draft.chapters if ch.chapter_number < from_chapter]
        draft.outlines = [o for o in draft.outlines if o.chapter_number < from_chapter]
        # Filter plot events for remaining chapters
        draft.plot_events = [e for e in draft.plot_events if e.chapter_number < from_chapter]
        # Clear character states (they reflect removed chapters' state)
        draft.character_states = []
        return draft
