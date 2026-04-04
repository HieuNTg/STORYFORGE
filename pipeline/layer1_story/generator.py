"""Layer 1: Story generation orchestrator."""

import logging

from models.schemas import Character, Chapter, StoryDraft, StoryContext
from services.llm_client import LLMClient
from services.input_sanitizer import sanitize_story_input
from config import ConfigManager
from pipeline.layer1_story.story_bible_manager import StoryBibleManager
from pipeline.layer1_story.character_generator import generate_characters, extract_character_states
from pipeline.layer1_story.chapter_writer import (
    build_chapter_prompt, write_chapter, write_chapter_stream,
    summarize_chapter, extract_plot_events,
)
from pipeline.layer1_story.outline_builder import suggest_titles, generate_world, generate_outline
from pipeline.layer1_story.post_processing import process_chapter_post_write
from pipeline.layer1_story.context_helpers import (
    get_rag_kb as _get_rag_kb_fn,
    write_chapter_with_long_context as _write_chapter_lc_fn,
)

logger = logging.getLogger(__name__)

# Backward-compat module-level wrappers
_get_rag_kb = _get_rag_kb_fn
_process_chapter_post_write = process_chapter_post_write


class StoryGenerator:
    """Generate complete stories from initial ideas."""

    LAYER = 1
    _layer_model = None  # Class-level default for __new__-based test compatibility

    # Token budget per chapter — can be overridden via subclassing or constructor kwarg
    TOKEN_BUDGET_PER_CHAPTER: int = 4000

    def __init__(self, token_budget_per_chapter: int = TOKEN_BUDGET_PER_CHAPTER):
        self.llm = LLMClient()
        self.config = ConfigManager()
        self.bible_manager = StoryBibleManager()
        self._long_ctx_client = None
        self._layer_model = self.llm.model_for_layer(self.LAYER)
        self.token_budget_per_chapter = token_budget_per_chapter

    @property
    def long_context_client(self):
        if self._long_ctx_client is None:
            from services.long_context_client import LongContextClient
            self._long_ctx_client = LongContextClient()
        return self._long_ctx_client

    def suggest_titles(self, genre: str, requirements: str = "") -> list[str]:
        return suggest_titles(self.llm, genre, requirements, model=self._layer_model)

    def generate_characters(self, title, genre, idea, num_characters=5) -> list[Character]:
        return generate_characters(self.llm, title, genre, idea, num_characters, model=self._layer_model)

    def generate_world(self, title, genre, characters):
        rag_kb = _get_rag_kb(self.config.pipeline.rag_persist_dir) if self.config.pipeline.rag_enabled else None
        return generate_world(self.llm, self.config, title, genre, characters, rag_kb=rag_kb, model=self._layer_model)

    def generate_outline(self, title, genre, characters, world, idea, num_chapters=10):
        return generate_outline(self.llm, title, genre, characters, world, idea, num_chapters, model=self._layer_model)

    def write_chapter(self, title, genre, style, characters, world, outline,
                      previous_summary="", word_count=2000, context=None) -> Chapter:
        rag_kb = _get_rag_kb(self.config.pipeline.rag_persist_dir) if self.config.pipeline.rag_enabled else None
        return write_chapter(self.llm, self.config, title, genre, style, characters, world, outline,
                             previous_summary, word_count, context, rag_kb=rag_kb, model=self._layer_model)

    def write_chapter_stream(self, title, genre, style, characters, world, outline,
                             word_count=2000, context=None, stream_callback=None) -> Chapter:
        rag_kb = _get_rag_kb(self.config.pipeline.rag_persist_dir) if self.config.pipeline.rag_enabled else None
        return write_chapter_stream(self.llm, self.config, title, genre, style, characters, world, outline,
                                    word_count, context, stream_callback, rag_kb=rag_kb, model=self._layer_model)

    def extract_character_states(self, content, characters):
        return extract_character_states(self.llm, content, characters)

    def extract_plot_events(self, content, chapter_number):
        return extract_plot_events(self.llm, content, chapter_number)

    def summarize_chapter(self, content):
        return summarize_chapter(self.llm, content)

    def _format_context(self, context, bible_context="", full_chapter_texts=None):
        from pipeline.layer1_story.chapter_writer import format_context
        return format_context(context, bible_context, full_chapter_texts)

    def _build_chapter_prompt(self, title, genre, style, characters, world, outline,
                               word_count, context=None, previous_summary="", bible_context="",
                               full_chapter_texts=None) -> tuple[str, str]:
        rag_kb = _get_rag_kb(self.config.pipeline.rag_persist_dir) if self.config.pipeline.rag_enabled else None
        return build_chapter_prompt(self.config, title, genre, style, characters, world, outline,
                                    word_count, context, previous_summary, bible_context, full_chapter_texts, rag_kb=rag_kb)

    @staticmethod
    def _excerpt(content: str, max_chars: int = 4000) -> str:
        from pipeline.layer1_story.chapter_writer import excerpt
        return excerpt(content, max_chars)

    def _get_self_reviewer(self):
        if not hasattr(self, '_self_reviewer'):
            from services.self_review import SelfReviewer
            self._self_reviewer = SelfReviewer(threshold=self.config.pipeline.self_review_threshold)
        return self._self_reviewer

    def _write_chapter_with_long_context(self, title, genre, style, characters, world, outline,
                                          word_count, story_context, all_chapter_texts, bible_ctx="") -> Chapter:
        return _write_chapter_lc_fn(self.llm, self.long_context_client, self.config,
                                    title, genre, style, characters, world, outline,
                                    word_count, story_context, all_chapter_texts, bible_ctx,
                                    layer_model=self._layer_model)

    def generate_full_story(self, title, genre, idea, style="Miêu tả chi tiết",
                             num_chapters=10, num_characters=5, word_count=2000,
                             progress_callback=None, stream_callback=None) -> StoryDraft:
        """Generate complete story from start to finish."""

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

        draft = StoryDraft(title=title, genre=genre, synopsis=synopsis,
                           characters=characters, world=world, outlines=outlines)
        story_context = StoryContext(total_chapters=len(outlines))
        bible_enabled = self.config.pipeline.story_bible_enabled
        if bible_enabled:
            draft.story_bible = self.bible_manager.initialize(draft, arc_size=self.config.pipeline.arc_size)

        # Delegate to BatchChapterGenerator (Phase 1: sequential within batches)
        from pipeline.layer1_story.batch_generator import BatchChapterGenerator
        batch_gen = BatchChapterGenerator(self)
        batch_gen.generate_chapters(
            draft=draft,
            outlines=outlines,
            story_context=story_context,
            title=title,
            genre=genre,
            style=style,
            characters=characters,
            world=world,
            word_count=word_count,
            progress_callback=progress_callback,
            stream_callback=stream_callback,
        )

        draft.character_states = list(story_context.character_states)
        draft.plot_events = list(story_context.plot_events)
        _log("Layer 1 hoàn tất - Bản thảo truyện đã sẵn sàng!")
        return draft

    def rebuild_context(self, draft: StoryDraft) -> StoryContext:
        """Rebuild StoryContext from existing StoryDraft chapters."""
        context_window = self.config.pipeline.context_window_chapters
        context = StoryContext(total_chapters=len(draft.chapters), current_chapter=len(draft.chapters))
        for ch in draft.chapters[-context_window:]:
            if ch.summary:
                context.recent_summaries.append(ch.summary)
            else:
                logger.warning(f"Chapter {ch.chapter_number} has no summary for context rebuild")
        context.character_states = list(draft.character_states)
        context.plot_events = list(draft.plot_events[-50:])
        return context

    def continue_story(self, draft: StoryDraft, additional_chapters=5, word_count=2000,
                       style="", progress_callback=None, stream_callback=None) -> StoryDraft:
        """Continue writing from existing StoryDraft by adding more chapters."""
        from pipeline.layer1_story.story_continuation import continue_story as _c
        return _c(self, draft, additional_chapters, word_count, style, progress_callback, stream_callback)

    @staticmethod
    def remove_chapters(draft: StoryDraft, from_chapter: int) -> StoryDraft:
        """Remove chapters from `from_chapter` onward. Returns modified draft."""
        draft.chapters = [ch for ch in draft.chapters if ch.chapter_number < from_chapter]
        draft.outlines = [o for o in draft.outlines if o.chapter_number < from_chapter]
        draft.plot_events = [e for e in draft.plot_events if e.chapter_number < from_chapter]
        draft.character_states = []
        return draft
