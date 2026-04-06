"""Batch-based chapter generation with optional parallel execution.

Phase 1: Sequential within batches, frozen context snapshots at batch boundaries.
Phase 2: asyncio.gather() within batches for true parallelism (gated by feature flag).
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Callable

from models.schemas import StoryDraft, StoryContext, ChapterOutline, Chapter
from pipeline.layer1_story.post_processing import process_chapter_post_write

logger = logging.getLogger(__name__)


class FrozenContext:
    """Immutable context snapshot taken at batch boundary."""

    __slots__ = ("recent_summaries", "character_states", "plot_events", "chapter_texts")

    def __init__(self, story_context: StoryContext, all_chapter_texts: list[str]):
        self.recent_summaries = list(story_context.recent_summaries)
        self.character_states = list(story_context.character_states)
        self.plot_events = list(story_context.plot_events)
        self.chapter_texts = list(all_chapter_texts)


class BatchChapterGenerator:
    """Generate chapters in batches with frozen context snapshots.

    When parallel_chapters_enabled=False (default), behaves identically to
    the original sequential loop in StoryGenerator.generate_full_story().

    When enabled, chapters within a batch share the same frozen context
    snapshot from the previous batch boundary, enabling future parallel
    execution without cross-chapter data races.
    """

    def __init__(self, story_generator):
        self.gen = story_generator
        self.config = story_generator.config
        self.llm = story_generator.llm
        self.batch_size = getattr(self.config.pipeline, "chapter_batch_size", 5)
        self.parallel_enabled = getattr(self.config.pipeline, "parallel_chapters_enabled", False)

    def generate_chapters(
        self,
        draft: StoryDraft,
        outlines: list[ChapterOutline],
        story_context: StoryContext,
        title: str,
        genre: str,
        style: str,
        characters: list,
        world,
        word_count: int = 2000,
        progress_callback: Optional[Callable] = None,
        stream_callback: Optional[Callable] = None,
        batch_checkpoint_callback: Optional[Callable] = None,
        resume_from_batch: int = 0,
        # NEW:
        macro_arcs=None,
        conflict_web=None,
        foreshadowing_plan=None,
    ) -> list[Chapter]:
        """Generate all chapters using batch strategy.

        Returns list of Chapter objects (also appended to draft.chapters).
        """
        all_chapter_texts: list[str] = []
        context_window = self.config.pipeline.context_window_chapters
        bible_enabled = self.config.pipeline.story_bible_enabled
        self_reviewer = (
            self.gen._get_self_reviewer()
            if self.config.pipeline.enable_self_review
            else None
        )

        # Initialize conflict map in story_context from conflict_web
        if conflict_web:
            story_context.conflict_map = list(conflict_web)

        def _log(msg):
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)

        batches = self._split_batches(outlines)
        mode = "parallel" if self.parallel_enabled else "sequential"
        _log(f"[BATCH] {len(outlines)} chương / {len(batches)} batch (size={self.batch_size}, mode={mode})")

        if resume_from_batch > 0:
            _log(f"[BATCH] Resuming from batch {resume_from_batch + 1}")

        with ThreadPoolExecutor(max_workers=3) as executor:
            for batch_idx, batch in enumerate(batches):
                if batch_idx < resume_from_batch:
                    continue

                frozen = FrozenContext(story_context, all_chapter_texts)
                _log(f"[BATCH] Batch {batch_idx + 1}/{len(batches)} ({len(batch)} chương)")

                if self.parallel_enabled and not stream_callback:
                    batch_chapters = self._run_batch_parallel(
                        batch=batch,
                        frozen=frozen,
                        draft=draft,
                        story_context=story_context,
                        all_chapter_texts=all_chapter_texts,
                        title=title,
                        genre=genre,
                        style=style,
                        characters=characters,
                        world=world,
                        word_count=word_count,
                        context_window=context_window,
                        bible_enabled=bible_enabled,
                        executor=executor,
                        self_reviewer=self_reviewer,
                        progress_callback=progress_callback,
                        macro_arcs=macro_arcs,
                        conflict_web=conflict_web,
                        foreshadowing_plan=foreshadowing_plan,
                    )
                else:
                    batch_chapters = self._run_batch_sequential(
                        batch=batch,
                        frozen=frozen,
                        draft=draft,
                        story_context=story_context,
                        all_chapter_texts=all_chapter_texts,
                        title=title,
                        genre=genre,
                        style=style,
                        characters=characters,
                        world=world,
                        word_count=word_count,
                        context_window=context_window,
                        bible_enabled=bible_enabled,
                        executor=executor,
                        self_reviewer=self_reviewer,
                        progress_callback=progress_callback,
                        stream_callback=stream_callback,
                        macro_arcs=macro_arcs,
                        conflict_web=conflict_web,
                        foreshadowing_plan=foreshadowing_plan,
                    )

                for ch in batch_chapters:
                    draft.chapters.append(ch)

                if batch_checkpoint_callback:
                    try:
                        batch_checkpoint_callback(batch_idx + 1, len(batches))
                    except Exception as e:
                        logger.warning("Batch checkpoint callback failed: %s", e)

        return list(draft.chapters)

    def _split_batches(self, outlines: list[ChapterOutline]) -> list[list[ChapterOutline]]:
        """Split outlines into batches of configured size."""
        bs = self.batch_size
        return [outlines[i : i + bs] for i in range(0, len(outlines), bs)]

    def _run_batch_sequential(
        self,
        batch: list[ChapterOutline],
        frozen: FrozenContext,
        draft: StoryDraft,
        story_context: StoryContext,
        all_chapter_texts: list[str],
        title: str,
        genre: str,
        style: str,
        characters: list,
        world,
        word_count: int,
        context_window: int,
        bible_enabled: bool,
        executor: ThreadPoolExecutor,
        self_reviewer,
        progress_callback,
        stream_callback,
        macro_arcs=None,
        conflict_web=None,
        foreshadowing_plan=None,
    ) -> list[Chapter]:
        """Run a single batch sequentially (Phase 1).

        Each chapter sees the live story_context which accumulates within
        the batch. The frozen snapshot is available for Phase 2 parallel mode.
        """
        chapters: list[Chapter] = []

        for outline in batch:
            story_context.current_chapter = outline.chapter_number

            bible_ctx = ""
            if bible_enabled and draft.story_bible:
                bible_ctx = self.gen.bible_manager.get_context_for_chapter(
                    draft.story_bible,
                    outline.chapter_number,
                    recent_summaries=list(story_context.recent_summaries),
                    character_states=list(story_context.character_states),
                )

            # Resolve per-chapter narrative context
            active_conflicts = []
            seeds = []
            payoffs = []
            pacing = ""
            try:
                from pipeline.layer1_story.macro_outline_builder import get_arc_for_chapter
                from pipeline.layer1_story.conflict_web_builder import get_active_conflicts
                from pipeline.layer1_story.foreshadowing_manager import get_seeds_to_plant, get_payoffs_due
                from pipeline.layer1_story.pacing_controller import validate_pacing
                current_arc = get_arc_for_chapter(macro_arcs or [], outline.chapter_number)
                arc_num = current_arc.arc_number if current_arc else 1
                active_conflicts = get_active_conflicts(conflict_web or [], arc_num)
                seeds = get_seeds_to_plant(foreshadowing_plan or [], outline.chapter_number)
                payoffs = get_payoffs_due(foreshadowing_plan or [], outline.chapter_number)
                pacing = validate_pacing(getattr(outline, "pacing_type", "") or "")
            except Exception as e:
                logger.warning("Narrative context resolution failed for ch%d: %s", outline.chapter_number, e)

            if progress_callback:
                progress_callback(
                    f"Đang viết chương {outline.chapter_number}: {outline.title}..."
                )

            if stream_callback:
                chapter = self.gen.write_chapter_stream(
                    title, genre, style, characters, world, outline,
                    word_count=word_count, context=story_context,
                    stream_callback=stream_callback,
                    open_threads=list(story_context.open_threads),
                    active_conflicts=active_conflicts,
                    foreshadowing_to_plant=seeds,
                    foreshadowing_to_payoff=payoffs,
                    pacing_type=pacing,
                )
            else:
                chapter = self.gen._write_chapter_with_long_context(
                    title, genre, style, characters, world, outline,
                    word_count, story_context, all_chapter_texts, bible_ctx,
                    open_threads=list(story_context.open_threads),
                    active_conflicts=active_conflicts,
                    foreshadowing_to_plant=seeds,
                    foreshadowing_to_payoff=payoffs,
                    pacing_type=pacing,
                )

            chapter_tokens_used = len(chapter.content) // 4
            usage_pct = (chapter_tokens_used / self.gen.token_budget_per_chapter) * 100
            if usage_pct >= 80:
                logger.warning(
                    "Chapter %d at %d%% of token budget (%d/%d estimated tokens)",
                    outline.chapter_number, int(usage_pct),
                    chapter_tokens_used, self.gen.token_budget_per_chapter,
                )

            chapters.append(chapter)
            all_chapter_texts.append(chapter.content)

            if progress_callback:
                progress_callback(
                    f"Đang trích xuất context chương {outline.chapter_number}..."
                )

            process_chapter_post_write(
                chapter, outline, story_context, characters, context_window,
                executor, self.llm, bible_enabled, draft, self.gen.bible_manager,
                progress_callback, genre, word_count,
                self.config.pipeline.enable_self_review, self_reviewer,
                open_threads=list(story_context.open_threads),
                foreshadowing_plan=foreshadowing_plan,
            )

        return chapters

    def _run_batch_parallel(
        self,
        batch: list[ChapterOutline],
        frozen: FrozenContext,
        draft: StoryDraft,
        story_context: StoryContext,
        all_chapter_texts: list[str],
        title: str,
        genre: str,
        style: str,
        characters: list,
        world,
        word_count: int,
        context_window: int,
        bible_enabled: bool,
        executor: ThreadPoolExecutor,
        self_reviewer,
        progress_callback,
        macro_arcs=None,
        conflict_web=None,
        foreshadowing_plan=None,
    ) -> list[Chapter]:
        """Run a single batch in parallel (Phase 2).

        All chapters in the batch use the frozen context snapshot.
        Post-processing runs sequentially after all chapters are written.
        """
        sibling_summaries = self._build_sibling_context(batch)
        # Capture frozen threads for parallel use
        frozen_threads = list(story_context.open_threads)

        def _write_one(outline: ChapterOutline) -> Chapter:
            bible_ctx = ""
            if bible_enabled and draft.story_bible:
                bible_ctx = self.gen.bible_manager.get_context_for_chapter(
                    draft.story_bible,
                    outline.chapter_number,
                    recent_summaries=frozen.recent_summaries,
                    character_states=frozen.character_states,
                )
            if sibling_summaries:
                bible_ctx = f"{bible_ctx}\n\n[Sibling outlines in this batch]\n{sibling_summaries}" if bible_ctx else f"[Sibling outlines in this batch]\n{sibling_summaries}"

            frozen_ctx = StoryContext(total_chapters=story_context.total_chapters)
            frozen_ctx.current_chapter = outline.chapter_number
            frozen_ctx.recent_summaries = list(frozen.recent_summaries)
            frozen_ctx.character_states = list(frozen.character_states)
            frozen_ctx.plot_events = list(frozen.plot_events)

            # Resolve per-chapter narrative context (non-fatal)
            active_conflicts = []
            seeds = []
            payoffs = []
            pacing = ""
            try:
                from pipeline.layer1_story.macro_outline_builder import get_arc_for_chapter
                from pipeline.layer1_story.conflict_web_builder import get_active_conflicts
                from pipeline.layer1_story.foreshadowing_manager import get_seeds_to_plant, get_payoffs_due
                from pipeline.layer1_story.pacing_controller import validate_pacing
                current_arc = get_arc_for_chapter(macro_arcs or [], outline.chapter_number)
                arc_num = current_arc.arc_number if current_arc else 1
                active_conflicts = get_active_conflicts(conflict_web or [], arc_num)
                seeds = get_seeds_to_plant(foreshadowing_plan or [], outline.chapter_number)
                payoffs = get_payoffs_due(foreshadowing_plan or [], outline.chapter_number)
                pacing = validate_pacing(getattr(outline, "pacing_type", "") or "")
            except Exception as e:
                logger.warning("Parallel narrative context resolution failed for ch%d: %s", outline.chapter_number, e)

            if progress_callback:
                progress_callback(
                    f"Đang viết chương {outline.chapter_number}: {outline.title}..."
                )

            return self.gen._write_chapter_with_long_context(
                title, genre, style, characters, world, outline,
                word_count, frozen_ctx, list(frozen.chapter_texts), bible_ctx,
                open_threads=frozen_threads,
                active_conflicts=active_conflicts,
                foreshadowing_to_plant=seeds,
                foreshadowing_to_payoff=payoffs,
                pacing_type=pacing,
            )

        max_workers = min(len(batch), 5)
        with ThreadPoolExecutor(max_workers=max_workers) as write_executor:
            futures = {
                write_executor.submit(_write_one, o): o for o in batch
            }
            chapters = []
            for future in as_completed(futures):
                try:
                    chapters.append(future.result())
                except Exception as e:
                    outline = futures[future]
                    logger.error("Parallel write failed for chapter %d: %s", outline.chapter_number, e)
                    raise

        chapters_ordered = sorted(chapters, key=lambda c: c.chapter_number)

        if progress_callback:
            progress_callback(
                f"[BATCH] {len(chapters_ordered)} chương viết xong, đang trích xuất context..."
            )

        for outline, chapter in zip(
            sorted(batch, key=lambda o: o.chapter_number), chapters_ordered
        ):
            all_chapter_texts.append(chapter.content)
            process_chapter_post_write(
                chapter, outline, story_context, characters, context_window,
                executor, self.llm, bible_enabled, draft, self.gen.bible_manager,
                progress_callback, genre, word_count,
                self.config.pipeline.enable_self_review, self_reviewer,
                open_threads=frozen_threads,
                foreshadowing_plan=foreshadowing_plan,
            )

        return chapters_ordered

    @staticmethod
    def _build_sibling_context(batch: list[ChapterOutline]) -> str:
        """Build sibling outline context for parallel chapters to avoid duplication."""
        if len(batch) <= 1:
            return ""
        lines = []
        for o in batch:
            lines.append(f"- Ch{o.chapter_number}: {o.title} — {o.summary}")
        return "\n".join(lines)
