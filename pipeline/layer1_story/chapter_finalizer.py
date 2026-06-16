"""ChapterFinalizer (P1-6): the post-write 4-call sequence + RAG indexing hook.

Extracted from batch_generator.py. finalize_chapter consolidates the previously
duplicated post-write block across the sync/async/threaded batch paths.
"""

import logging
from typing import Callable

from models.schemas import Chapter, ChapterOutline, StoryContext
from pipeline.layer1_story.post_processing import process_chapter_post_write
from pipeline.layer1_story.chapter_payoff_rewrite import (
    _verify_and_rewrite_missing_payoffs,
)
from pipeline.layer1_story.chapter_rewrites import (
    _enforce_pacing,
    _rewrite_for_consistency_violations,
)

logger = logging.getLogger(__name__)


def finalize_chapter(
    *,
    pipeline_config,
    llm,
    chapter: Chapter,
    outline: ChapterOutline,
    story_context: StoryContext,
    characters: list,
    context_window: int,
    executor,
    draft,
    bible_manager,
    progress_callback: Callable | None,
    genre: str,
    word_count: int,
    enable_self_review: bool,
    self_reviewer,
    open_threads: list,
    foreshadowing_plan: list | None,
    layer_model: str | None,
) -> None:
    """P1-6 ChapterFinalizer: run the post-write 4-call sequence in one place.

    Consolidates the previously duplicated block in three call sites
    (sync executor path, async gather path, and serial fallback path) so
    behavioural drift across paths is no longer possible.

    Steps (in order, all in-place mutations on `chapter`/`story_context`):
      1. process_chapter_post_write — extracts, summaries, RAG, etc.
      2. verify-and-rewrite missing foreshadowing payoffs
      3. consistency-violation rewrite
      4. pacing enforcement rewrite

    Not safe for concurrent invocation against a shared `story_context`:
    the 4 inner steps mutate context state in order and read each other's
    output (e.g., consistency rewrite reads plot_events written by step 1).
    Call sequentially per chapter.
    """
    process_chapter_post_write(
        chapter,
        outline,
        story_context,
        characters,
        context_window,
        executor,
        llm,
        draft,
        bible_manager,
        progress_callback,
        genre,
        word_count,
        enable_self_review,
        self_reviewer,
        open_threads=open_threads,
        foreshadowing_plan=foreshadowing_plan,
        world_rules=getattr(draft.world, "rules", None) or [],
        voice_profiles=getattr(draft, "voice_profiles", None) or [],
        pipeline_config=pipeline_config,
    )

    _verify_and_rewrite_missing_payoffs(
        pipeline_config,
        llm,
        chapter,
        outline,
        story_context,
        foreshadowing_plan,
        layer_model,
        progress_callback,
        draft=draft,
    )

    _rewrite_for_consistency_violations(
        pipeline_config,
        llm,
        chapter,
        outline,
        story_context,
        layer_model,
        progress_callback,
        draft=draft,
    )

    _enforce_pacing(
        pipeline_config,
        llm,
        chapter,
        outline,
        layer_model,
        progress_callback,
        draft=draft,
    )


def _index_chapter_into_rag(
    config,
    chapter: Chapter,
    outline: ChapterOutline,
    characters: list,
    open_threads: list | None,
) -> int:
    """Post-write hook: push chapter chunks into the shared RAG singleton.

    Gated by rag_enabled AND rag_index_chapters flags. Silent no-op if RAG
    unavailable (never blocks pipeline). Returns chunks added (for analytics).
    """
    if not getattr(config.pipeline, "rag_enabled", False):
        return 0
    if not getattr(config.pipeline, "rag_index_chapters", False):
        return 0
    try:
        import time as _time
        from pipeline.layer1_story.context_helpers import get_rag_kb
        from services.trace_context import get_module, set_module, get_trace

        kb = get_rag_kb(config.pipeline.rag_persist_dir)
        if kb is None or not getattr(kb, "is_available", False):
            return 0
        _prev = get_module()
        set_module("rag_index")
        try:
            chars = [
                getattr(c, "name", "")
                for c in (characters or [])
                if getattr(c, "name", "")
            ]
            threads = [
                (getattr(t, "thread_id", None) or getattr(t, "title", ""))
                for t in (open_threads or [])
                if (getattr(t, "thread_id", None) or getattr(t, "title", ""))
            ]
            _t0 = _time.perf_counter()
            chunks_added = kb.index_chapter(
                chapter_number=chapter.chapter_number,
                content=chapter.content,
                characters=chars,
                threads=threads,
                summary=getattr(outline, "summary", "") or "",
            )
            _dur_ms = (_time.perf_counter() - _t0) * 1000.0
            _tr = get_trace()
            if _tr is not None:
                _tr.rag_stats.record_index(int(chunks_added or 0), _dur_ms)
            return chunks_added
        finally:
            set_module(_prev or "chapter_writer")
    except Exception as e:
        logger.debug(
            f"RAG index failed for ch{chapter.chapter_number} (non-fatal): {e}"
        )
        return 0
