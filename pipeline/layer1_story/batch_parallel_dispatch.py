"""Parallel/threaded batch-dispatch helpers for BatchChapterGenerator.

Extracted verbatim from ``batch_generator`` (structural split, no behavior
change). Provides ``ParallelDispatchMixin``, mixed into
``BatchChapterGenerator`` so ``self._run_batch_parallel`` /
``self._run_batch_threaded`` calls resolve exactly as before.

Note: ``_run_batch_async`` deliberately stays in ``batch_generator`` because it
references the module-global ``_index_chapter_into_rag`` that tests patch via
``pipeline.layer1_story.batch_generator._index_chapter_into_rag``.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from models.schemas import StoryDraft, StoryContext, ChapterOutline, Chapter
from pipeline.layer1_story.chapter_finalizer import finalize_chapter
from pipeline.layer1_story.contract_batch_retry import validate_and_retry_threaded

from pipeline.layer1_story.batch_context import CausalAccumulator, FrozenContext

logger = logging.getLogger(__name__)


class ParallelDispatchMixin:
    """Batch-level parallel routing + thread-pool execution fallback."""

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
        executor: ThreadPoolExecutor,
        self_reviewer,
        progress_callback,
        macro_arcs=None,
        conflict_web=None,
        foreshadowing_plan=None,
        premise=None,
        voice_profiles=None,
        idea: str = "",
        idea_summary: str = "",
    ) -> list[Chapter]:
        """Run a single batch in parallel (Phase 2/3).

        Improvements:
        - #1: Uses asyncio.gather() when parallel_use_asyncio=True
        - #2: Contract validation with retry
        - #3: Cross-batch causal sync via CausalAccumulator
        """
        # Route to async or thread-based implementation
        if self.use_asyncio:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                # Already in async context — run directly
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self._run_batch_async(
                            batch,
                            frozen,
                            draft,
                            story_context,
                            all_chapter_texts,
                            title,
                            genre,
                            style,
                            characters,
                            world,
                            word_count,
                            context_window,
                            executor,
                            self_reviewer,
                            progress_callback,
                            macro_arcs,
                            conflict_web,
                            foreshadowing_plan,
                            premise,
                            voice_profiles,
                            idea,
                            idea_summary,
                        ),
                    )
                    return future.result()
            else:
                return asyncio.run(
                    self._run_batch_async(
                        batch,
                        frozen,
                        draft,
                        story_context,
                        all_chapter_texts,
                        title,
                        genre,
                        style,
                        characters,
                        world,
                        word_count,
                        context_window,
                        executor,
                        self_reviewer,
                        progress_callback,
                        macro_arcs,
                        conflict_web,
                        foreshadowing_plan,
                        premise,
                        voice_profiles,
                        idea,
                        idea_summary,
                    )
                )
        else:
            return self._run_batch_threaded(
                batch,
                frozen,
                draft,
                story_context,
                all_chapter_texts,
                title,
                genre,
                style,
                characters,
                world,
                word_count,
                context_window,
                executor,
                self_reviewer,
                progress_callback,
                macro_arcs,
                conflict_web,
                foreshadowing_plan,
                premise,
                voice_profiles,
                idea,
                idea_summary,
            )

    def _run_batch_threaded(
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
        executor: ThreadPoolExecutor,
        self_reviewer,
        progress_callback,
        macro_arcs=None,
        conflict_web=None,
        foreshadowing_plan=None,
        premise=None,
        voice_profiles=None,
        idea: str = "",
        idea_summary: str = "",
    ) -> list[Chapter]:
        """Thread-based batch execution (fallback when asyncio disabled)."""
        sibling_summaries = self._build_sibling_context(batch)
        frozen_threads = list(story_context.open_threads)

        from pipeline.layer1_story.enhancement_context_builder import (
            build_shared_enhancement_context,
        )

        shared_enhancement = build_shared_enhancement_context(
            self.config,
            genre,
            premise=premise,
            voice_profiles=voice_profiles,
        )

        causal_acc = CausalAccumulator() if self.causal_sync else None

        max_workers = min(len(batch), 5)
        with ThreadPoolExecutor(max_workers=max_workers) as write_executor:
            futures = {
                write_executor.submit(
                    self._write_chapter_parallel,
                    o,
                    frozen,
                    draft,
                    story_context,
                    frozen_threads,
                    sibling_summaries,
                    shared_enhancement,
                    title,
                    genre,
                    style,
                    characters,
                    world,
                    word_count,
                    macro_arcs,
                    conflict_web,
                    foreshadowing_plan,
                    progress_callback,
                    causal_acc,
                    idea,
                    idea_summary,
                ): o
                for o in batch
            }
            chapters = []
            contracts = {}
            for future in as_completed(futures):
                outline = futures[future]
                try:
                    chapter, contract = future.result()
                    chapters.append(chapter)
                    if contract:
                        contracts[chapter.chapter_number] = contract
                except Exception as e:
                    logger.error(
                        "Threaded write failed for chapter %d: %s",
                        outline.chapter_number,
                        e,
                    )
                    raise

        # Contract validation with retry (#2 improvement)
        chapters = validate_and_retry_threaded(
            self,
            chapters=chapters,
            contracts=contracts,
            batch=batch,
            frozen=frozen,
            draft=draft,
            story_context=story_context,
            frozen_threads=frozen_threads,
            sibling_summaries=sibling_summaries,
            shared_enhancement=shared_enhancement,
            title=title,
            genre=genre,
            style=style,
            characters=characters,
            world=world,
            word_count=word_count,
            macro_arcs=macro_arcs,
            conflict_web=conflict_web,
            foreshadowing_plan=foreshadowing_plan,
            progress_callback=progress_callback,
            idea=idea,
            idea_summary=idea_summary,
        )

        chapters_ordered = sorted(chapters, key=lambda c: c.chapter_number)

        # Causal sync (#3 improvement)
        if causal_acc and self.causal_sync:
            self._sync_causal_events(causal_acc, story_context, progress_callback)

        if progress_callback:
            progress_callback(
                f"[BATCH] {len(chapters_ordered)} chương viết xong, đang trích xuất context..."
            )

        for outline, chapter in zip(
            sorted(batch, key=lambda o: o.chapter_number), chapters_ordered
        ):
            all_chapter_texts.append(chapter.content)
            finalize_chapter(
                pipeline_config=self.config.pipeline,
                llm=self.llm,
                chapter=chapter,
                outline=outline,
                story_context=story_context,
                characters=characters,
                context_window=context_window,
                executor=executor,
                draft=draft,
                bible_manager=self.gen.bible_manager,
                progress_callback=progress_callback,
                genre=genre,
                word_count=word_count,
                enable_self_review=self.config.pipeline.enable_self_review,
                self_reviewer=self_reviewer,
                open_threads=frozen_threads,
                foreshadowing_plan=foreshadowing_plan,
                layer_model=self.gen._layer_model,
            )

        return chapters_ordered
