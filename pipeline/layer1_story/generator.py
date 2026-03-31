"""Layer 1: Story generation orchestrator."""

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from models.schemas import (
    Character, ChapterOutline, Chapter, StoryDraft,
    StoryContext, count_words,
)
from services.llm_client import LLMClient
from services import prompts
from services.input_sanitizer import sanitize_story_input
from config import ConfigManager
from pipeline.layer1_story.story_bible_manager import StoryBibleManager
from pipeline.layer1_story.character_generator import (
    generate_characters, extract_character_states,
)
from pipeline.layer1_story.chapter_writer import (
    build_chapter_prompt, write_chapter, write_chapter_stream,
    summarize_chapter, extract_plot_events,
)
from pipeline.layer1_story.outline_builder import (
    suggest_titles, generate_world, generate_outline,
)

logger = logging.getLogger(__name__)

# Lazy singleton — only instantiated when rag_enabled=True
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


def _prune_plot_events(events: list) -> list:
    """Smart prune: keep recent 30 + top-20 older by event length. Cap 50."""
    if len(events) <= 50:
        return events
    recent = events[-30:]
    older = sorted(events[:-30], key=lambda e: len(e.event), reverse=True)[:20]
    return older + recent


def _process_chapter_post_write(
    chapter: Chapter,
    outline: ChapterOutline,
    story_context: StoryContext,
    characters: list[Character],
    context_window: int,
    executor: ThreadPoolExecutor,
    llm: LLMClient,
    bible_enabled: bool,
    draft: StoryDraft,
    bible_manager: StoryBibleManager,
    progress_callback=None,
    genre: str = "",
    word_count: int = 2000,
    enable_self_review: bool = False,
    self_reviewer=None,
) -> tuple[Chapter, str, list, list]:
    """Shared post-write logic: self-review, parallel extraction, context update, bible update.

    Returns (chapter, summary, new_states, new_events) — but also mutates story_context in place.
    """
    # Optional self-review
    if enable_self_review and self_reviewer is not None:
        revised_content, review_scores = self_reviewer.review_and_revise(
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

    # Parallel extraction
    summary_f = executor.submit(summarize_chapter, llm, chapter.content)
    states_f = executor.submit(extract_character_states, llm, chapter.content, characters)
    events_f = executor.submit(extract_plot_events, llm, chapter.content, outline.chapter_number)

    _TIMEOUT = 120
    try:
        summary = summary_f.result(timeout=_TIMEOUT)
    except Exception as e:
        logger.warning(f"Summary extraction failed: {e}")
        summary = ""
        summary_f.cancel()

    try:
        new_states = states_f.result(timeout=_TIMEOUT)
    except Exception as e:
        logger.warning(f"Character state extraction failed: {e}")
        new_states = []
        states_f.cancel()

    try:
        new_events = events_f.result(timeout=_TIMEOUT)
    except Exception as e:
        logger.warning(f"Plot event extraction failed: {e}")
        new_events = []
        events_f.cancel()

    # Update rolling context
    chapter.summary = summary
    story_context.recent_summaries.append(summary)
    story_context.recent_summaries = story_context.recent_summaries[-context_window:]

    if new_states:
        existing = {s.name: s for s in story_context.character_states}
        for s in new_states:
            existing[s.name] = s
        story_context.character_states = list(existing.values())

    story_context.plot_events.extend(new_events)
    story_context.plot_events = _prune_plot_events(story_context.plot_events)

    # Update Story Bible
    if bible_enabled and draft.story_bible:
        bible_manager.update_after_chapter(
            draft.story_bible, chapter,
            list(story_context.character_states), new_events,
        )

    return chapter, summary, new_states, new_events


class StoryGenerator:
    """Generate complete stories from initial ideas."""

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

    # --- Delegating public API methods (preserve original signatures) ---

    def suggest_titles(self, genre: str, requirements: str = "") -> list[str]:
        return suggest_titles(self.llm, genre, requirements)

    def generate_characters(
        self, title: str, genre: str, idea: str, num_characters: int = 5
    ) -> list[Character]:
        return generate_characters(self.llm, title, genre, idea, num_characters)

    def generate_world(self, title: str, genre: str, characters: list[Character]):
        rag_kb = _get_rag_kb(self.config.pipeline.rag_persist_dir) if self.config.pipeline.rag_enabled else None
        return generate_world(self.llm, self.config, title, genre, characters, rag_kb=rag_kb)

    def generate_outline(self, title, genre, characters, world, idea, num_chapters=10):
        return generate_outline(self.llm, title, genre, characters, world, idea, num_chapters)

    def write_chapter(
        self, title, genre, style, characters, world, outline,
        previous_summary="", word_count=2000, context=None,
    ) -> Chapter:
        rag_kb = _get_rag_kb(self.config.pipeline.rag_persist_dir) if self.config.pipeline.rag_enabled else None
        return write_chapter(
            self.llm, self.config, title, genre, style, characters, world, outline,
            previous_summary, word_count, context, rag_kb=rag_kb,
        )

    def write_chapter_stream(
        self, title, genre, style, characters, world, outline,
        word_count=2000, context=None, stream_callback=None,
    ) -> Chapter:
        rag_kb = _get_rag_kb(self.config.pipeline.rag_persist_dir) if self.config.pipeline.rag_enabled else None
        return write_chapter_stream(
            self.llm, self.config, title, genre, style, characters, world, outline,
            word_count, context, stream_callback, rag_kb=rag_kb,
        )

    def extract_character_states(self, content, characters):
        return extract_character_states(self.llm, content, characters)

    def extract_plot_events(self, content, chapter_number):
        return extract_plot_events(self.llm, content, chapter_number)

    def summarize_chapter(self, content):
        return summarize_chapter(self.llm, content)

    # Internal helpers kept for backward compat (orchestrator/tests may call them)
    def _format_context(self, context, bible_context="", full_chapter_texts=None):
        from pipeline.layer1_story.chapter_writer import format_context
        return format_context(context, bible_context, full_chapter_texts)

    def _build_chapter_prompt(
        self, title, genre, style, characters, world, outline,
        word_count, context=None, previous_summary="", bible_context="",
        full_chapter_texts=None,
    ) -> tuple[str, str]:
        rag_kb = _get_rag_kb(self.config.pipeline.rag_persist_dir) if self.config.pipeline.rag_enabled else None
        return build_chapter_prompt(
            self.config, title, genre, style, characters, world, outline,
            word_count, context, previous_summary, bible_context,
            full_chapter_texts, rag_kb=rag_kb,
        )

    @staticmethod
    def _excerpt(content: str, max_chars: int = 4000) -> str:
        from pipeline.layer1_story.chapter_writer import excerpt
        return excerpt(content, max_chars)

    def _get_self_reviewer(self):
        if not hasattr(self, '_self_reviewer'):
            from services.self_review import SelfReviewer
            self._self_reviewer = SelfReviewer(
                threshold=self.config.pipeline.self_review_threshold
            )
        return self._self_reviewer

    def _write_chapter_with_long_context(
        self, title, genre, style, characters, world, outline,
        word_count, story_context, all_chapter_texts, bible_ctx="",
    ) -> Chapter:
        """Try long-context generation; fall back to standard if disabled/overflow."""
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

        rag_kb = _get_rag_kb(self.config.pipeline.rag_persist_dir) if self.config.pipeline.rag_enabled else None
        sys_prompt, user_prompt = build_chapter_prompt(
            self.config, title, genre, style, characters, world, outline,
            word_count, story_context, bible_context=bible_ctx,
            full_chapter_texts=all_chapter_texts if use_lc else None,
            rag_kb=rag_kb,
        )
        if use_lc:
            content = self.long_context_client.generate(
                system_prompt=sys_prompt, user_prompt=user_prompt, max_tokens=8192,
            )
        else:
            content = self.llm.generate(
                system_prompt=sys_prompt, user_prompt=user_prompt, max_tokens=8192,
            )
        return Chapter(
            chapter_number=outline.chapter_number,
            title=outline.title,
            content=content,
            word_count=count_words(content),
        )

    # --- Core pipeline methods ---

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
        """Generate complete story from start to finish."""
        context_window = self.config.pipeline.context_window_chapters

        def _log(msg):
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)

        _san = sanitize_story_input(title=title, idea=idea, genre=genre)
        if not _san.is_safe:
            logger.warning(f"Injection threats in story input: {_san.threats_found}")
            if self.config.pipeline.block_on_injection:
                from errors.exceptions import InputSanitizationError
                raise InputSanitizationError(_san.threats_found)

        _log(f"Đang tạo nhân vật cho '{title}'...")
        characters = self.generate_characters(title, genre, idea, num_characters)

        _log("Đang xây dựng bối cảnh thế giới...")
        world = self.generate_world(title, genre, characters)

        _log(f"Đang tạo dàn ý {num_chapters} chương...")
        synopsis, outlines = self.generate_outline(title, genre, characters, world, idea, num_chapters)

        draft = StoryDraft(
            title=title, genre=genre, synopsis=synopsis,
            characters=characters, world=world, outlines=outlines,
        )
        story_context = StoryContext(total_chapters=len(outlines))

        bible_enabled = self.config.pipeline.story_bible_enabled
        if bible_enabled:
            draft.story_bible = self.bible_manager.initialize(
                draft, arc_size=self.config.pipeline.arc_size
            )

        all_chapter_texts: list[str] = []
        self_reviewer = self._get_self_reviewer() if self.config.pipeline.enable_self_review else None

        with ThreadPoolExecutor(max_workers=3) as executor:
            for outline in outlines:
                story_context.current_chapter = outline.chapter_number

                bible_ctx = ""
                if bible_enabled and draft.story_bible:
                    bible_ctx = self.bible_manager.get_context_for_chapter(
                        draft.story_bible, outline.chapter_number,
                        recent_summaries=list(story_context.recent_summaries),
                        character_states=list(story_context.character_states),
                    )

                _log(f"Đang viết chương {outline.chapter_number}: {outline.title}...")
                if stream_callback:
                    chapter = self.write_chapter_stream(
                        title, genre, style, characters, world, outline,
                        word_count=word_count, context=story_context,
                        stream_callback=stream_callback,
                    )
                else:
                    chapter = self._write_chapter_with_long_context(
                        title, genre, style, characters, world, outline,
                        word_count, story_context, all_chapter_texts, bible_ctx,
                    )

                draft.chapters.append(chapter)
                all_chapter_texts.append(chapter.content)

                _log(f"Đang trích xuất context chương {outline.chapter_number}...")
                _process_chapter_post_write(
                    chapter, outline, story_context, characters, context_window,
                    executor, self.llm, bible_enabled, draft, self.bible_manager,
                    progress_callback, genre, word_count,
                    self.config.pipeline.enable_self_review, self_reviewer,
                )

        draft.character_states = list(story_context.character_states)
        draft.plot_events = list(story_context.plot_events)
        _log("Layer 1 hoàn tất - Bản thảo truyện đã sẵn sàng!")
        return draft

    def rebuild_context(self, draft: StoryDraft) -> StoryContext:
        """Rebuild StoryContext from existing StoryDraft chapters."""
        context_window = self.config.pipeline.context_window_chapters
        context = StoryContext(
            total_chapters=len(draft.chapters),
            current_chapter=len(draft.chapters),
        )
        for ch in draft.chapters[-context_window:]:
            if ch.summary:
                context.recent_summaries.append(ch.summary)
            else:
                logger.warning(f"Chapter {ch.chapter_number} has no summary for context rebuild")
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
        _log(f"Generating outlines for chapters {start_chapter}-{start_chapter + additional_chapters - 1}...")

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
            _log("No outlines generated. Aborting continuation.")
            return draft

        draft.outlines.extend(new_outlines)
        story_context = self.rebuild_context(draft)
        all_chapter_texts = [ch.content for ch in draft.chapters if ch.content]

        final_total = len(draft.chapters) + len(new_outlines)
        self_reviewer = self._get_self_reviewer() if self.config.pipeline.enable_self_review else None

        with ThreadPoolExecutor(max_workers=3) as executor:
            for outline in new_outlines:
                story_context.current_chapter = outline.chapter_number
                story_context.total_chapters = final_total

                _log(f"Writing chapter {outline.chapter_number}: {outline.title}...")
                if stream_callback:
                    chapter = self.write_chapter_stream(
                        draft.title, draft.genre, effective_style,
                        draft.characters, draft.world, outline,
                        word_count=word_count, context=story_context,
                        stream_callback=stream_callback,
                    )
                else:
                    chapter = self._write_chapter_with_long_context(
                        draft.title, draft.genre, effective_style,
                        draft.characters, draft.world, outline,
                        word_count, story_context, all_chapter_texts,
                    )

                draft.chapters.append(chapter)
                all_chapter_texts.append(chapter.content)

                _log(f"Extracting context for chapter {outline.chapter_number}...")
                _process_chapter_post_write(
                    chapter, outline, story_context, draft.characters, context_window,
                    executor, self.llm, False, draft, self.bible_manager,
                    progress_callback, draft.genre, word_count,
                    self.config.pipeline.enable_self_review, self_reviewer,
                )

        draft.character_states = list(story_context.character_states)
        draft.plot_events = list(story_context.plot_events)
        _log(f"Continuation complete — {len(new_outlines)} chapters added!")
        return draft

    @staticmethod
    def remove_chapters(draft: StoryDraft, from_chapter: int) -> StoryDraft:
        """Remove chapters from `from_chapter` onward. Returns modified draft."""
        draft.chapters = [ch for ch in draft.chapters if ch.chapter_number < from_chapter]
        draft.outlines = [o for o in draft.outlines if o.chapter_number < from_chapter]
        draft.plot_events = [e for e in draft.plot_events if e.chapter_number < from_chapter]
        draft.character_states = []
        return draft
