"""Batch-based chapter generation with optional parallel execution.

Phase 1: Sequential within batches, frozen context snapshots at batch boundaries.
Phase 2: asyncio.gather() within batches for true parallelism (gated by feature flag).
Phase 3: Contract retry + cross-batch causal sync.
"""

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional, Callable

from models.schemas import StoryDraft, StoryContext, ChapterOutline, Chapter
from pipeline.layer1_story.chapter_finalizer import (
    finalize_chapter,
    _index_chapter_into_rag,
)
from pipeline.layer1_story.chapter_context_assembler import (
    assemble_chapter_write_context,
)
from pipeline.layer1_story.chapter_critique_runner import run_chapter_self_critique
from pipeline.layer1_story.enhancement_injections import (
    build_chapter_enhancement_context,
)
from pipeline.layer1_story.context_helpers import get_rag_batch_cache
from pipeline.layer1_story.chapter_contract_setup import build_contract_for_chapter
from pipeline.layer1_story.scene_write_prep import (
    prepare_scene_context_and_beat_chapter,
)
from pipeline.layer1_story.sequential_write_dispatch import write_sequential_chapter
from pipeline.layer1_story.contract_batch_retry import validate_and_retry_threaded
from pipeline.layer1_story.contract_validation_retry import (
    validate_and_retry_contract,
)
from pipeline.layer1_story.parallel_write_context import (
    assemble_parallel_write_inputs,
)

logger = logging.getLogger(__name__)


@dataclass
class CausalAccumulator:
    """Thread-safe accumulator for causal events across parallel chapters.

    Used to sync causal graph updates after parallel batch completes.
    """

    events: list[dict] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def add_event(
        self,
        chapter_num: int,
        event_type: str,
        description: str,
        causes: list[int] = None,
        effects: list[int] = None,
    ):
        with self._lock:
            self.events.append(
                {
                    "chapter": chapter_num,
                    "type": event_type,
                    "description": description,
                    "causes": causes or [],
                    "effects": effects or [],
                }
            )

    def get_events_sorted(self) -> list[dict]:
        with self._lock:
            return sorted(self.events, key=lambda e: e["chapter"])

    def clear(self):
        with self._lock:
            self.events.clear()


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
        self.parallel_enabled = getattr(
            self.config.pipeline, "parallel_chapters_enabled", False
        )
        self.use_asyncio = getattr(self.config.pipeline, "parallel_use_asyncio", True)
        # When True, force sequential within-batch execution so each chapter's
        # continuity anchor is the freshly-completed predecessor (not a stale
        # prior-batch tail). Overrides parallel_enabled at dispatch time.
        # Use `is True` so MagicMock auto-vivified attributes in tests don't
        # accidentally trip strict mode (those tests want parallel behaviour).
        self.strict_continuity = (
            getattr(self.config.pipeline, "l1_strict_chapter_continuity", False) is True
        )
        self.retry_max = getattr(self.config.pipeline, "chapter_retry_max", 2)
        self.retry_threshold = getattr(
            self.config.pipeline, "chapter_retry_threshold", 0.6
        )
        self.causal_sync = getattr(self.config.pipeline, "parallel_causal_sync", True)

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
        chapter_complete_callback: Optional[Callable] = None,
        resume_from_batch: int = 0,
        # NEW:
        macro_arcs=None,
        conflict_web=None,
        foreshadowing_plan=None,
        premise=None,
        voice_profiles=None,
        idea: str = "",
        idea_summary: str = "",
    ) -> list[Chapter]:
        """Generate all chapters using batch strategy.

        Returns list of Chapter objects (also appended to draft.chapters).
        """
        all_chapter_texts: list[str] = []
        context_window = self.config.pipeline.context_window_chapters
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
        if self.parallel_enabled and self.strict_continuity:
            mode = "sequential (strict-continuity override)"
        elif self.parallel_enabled:
            mode = "parallel"
        else:
            mode = "sequential"
        _log(
            f"[BATCH] {len(outlines)} chương / {len(batches)} batch (size={self.batch_size}, mode={mode})"
        )

        if resume_from_batch > 0:
            _log(f"[BATCH] Resuming from batch {resume_from_batch + 1}")

        # P2: scale executor with batch size — each chapter spawns multiple
        # blocking helper calls (extraction/summary/rewrite); fixed cap of 3
        # was a serial bottleneck for batch_size >= 3.
        _max_workers = max(3, int(getattr(self, "batch_size", 3) or 3) * 3)
        with ThreadPoolExecutor(max_workers=_max_workers) as executor:
            for batch_idx, batch in enumerate(batches):
                if batch_idx < resume_from_batch:
                    continue

                frozen = FrozenContext(story_context, all_chapter_texts)
                # Bug #4: Reset RAG cache at batch boundary
                get_rag_batch_cache().reset_batch()
                _log(
                    f"[BATCH] Batch {batch_idx + 1}/{len(batches)} ({len(batch)} chương)"
                )

                if (
                    self.parallel_enabled
                    and not stream_callback
                    and not self.strict_continuity
                ):
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
                        executor=executor,
                        self_reviewer=self_reviewer,
                        progress_callback=progress_callback,
                        macro_arcs=macro_arcs,
                        conflict_web=conflict_web,
                        foreshadowing_plan=foreshadowing_plan,
                        premise=premise,
                        voice_profiles=voice_profiles,
                        idea=idea,
                        idea_summary=idea_summary,
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
                        executor=executor,
                        self_reviewer=self_reviewer,
                        progress_callback=progress_callback,
                        stream_callback=stream_callback,
                        macro_arcs=macro_arcs,
                        conflict_web=conflict_web,
                        foreshadowing_plan=foreshadowing_plan,
                        premise=premise,
                        voice_profiles=voice_profiles,
                        idea=idea,
                        idea_summary=idea_summary,
                    )

                for ch in batch_chapters:
                    draft.chapters.append(ch)
                    if chapter_complete_callback:
                        try:
                            chapter_complete_callback(ch, draft, len(outlines))
                        except Exception as e:
                            logger.warning(
                                "chapter_complete_callback failed (non-fatal): %s", e
                            )

                # Context health check (Sprint 1 Task 1)
                self._check_context_health(story_context, batch_idx, _log)

                if batch_checkpoint_callback:
                    try:
                        batch_checkpoint_callback(batch_idx + 1, len(batches))
                    except Exception as e:
                        logger.warning("Batch checkpoint callback failed: %s", e)

        return list(draft.chapters)

    def _check_context_health(self, story_context, batch_idx: int, _log) -> None:
        """Monitor extraction_health; halt pipeline when context corruption crosses threshold.

        Halt rule: 3 consecutive chapters each having >=3 failed extractions.
        That requires ~9+ failures concentrated in recent chapters — well above
        transient LLM noise, so won't false-positive on single rate-limit blips.
        """
        score = story_context.compute_health_score(lookback=10)
        _log(f"[HEALTH] batch {batch_idx + 1} health={score:.0%}")

        if score < 0.7:
            _log(
                f"[HEALTH] ⚠️ Context health {score:.0%} < 70% — recent extractions "
                f"failing frequently, subsequent chapters may build on stale state"
            )

        # Circuit breaker: 3 consecutive recent chapters w/ >=3 failures each
        recent_chapters = sorted(
            {e.chapter_number for e in story_context.extraction_health[-60:]}
        )[-3:]
        if len(recent_chapters) < 3:
            return
        bad_chapters = sum(
            1
            for ch in recent_chapters
            if len(story_context.failed_extractions_in_last_chapter(ch)) >= 3
        )
        if bad_chapters >= 3:
            raise RuntimeError(
                f"Context corruption detected: 3 consecutive chapters ({recent_chapters}) "
                f"with >=3 extraction failures each. Health score: {score:.0%}. "
                f"Pipeline halted to prevent building on corrupted state. "
                f"Check LLM connectivity / rate limits / API key."
            )

    def _split_batches(
        self, outlines: list[ChapterOutline]
    ) -> list[list[ChapterOutline]]:
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
        executor: ThreadPoolExecutor,
        self_reviewer,
        progress_callback,
        stream_callback,
        macro_arcs=None,
        conflict_web=None,
        foreshadowing_plan=None,
        premise=None,
        voice_profiles=None,
        idea: str = "",
        idea_summary: str = "",
    ) -> list[Chapter]:
        """Run a single batch sequentially (Phase 1).

        Each chapter sees the live story_context which accumulates within
        the batch. The frozen snapshot is available for Phase 2 parallel mode.
        """
        chapters: list[Chapter] = []
        _contract_failures: list[str] = []

        for outline in batch:
            story_context.current_chapter = outline.chapter_number
            try:
                from services.trace_context import set_chapter, set_module

                set_chapter(outline.chapter_number)
                set_module("chapter_writer")
            except Exception:
                pass

            (
                bible_ctx,
                active_conflicts,
                seeds,
                payoffs,
                pacing,
                arc_context,
            ) = assemble_chapter_write_context(
                self.config,
                bible_manager=self.gen.bible_manager,
                draft=draft,
                outline=outline,
                batch=batch,
                story_context=story_context,
                all_chapter_texts=all_chapter_texts,
                macro_arcs=macro_arcs,
                conflict_web=conflict_web,
                foreshadowing_plan=foreshadowing_plan,
            )

            if progress_callback:
                progress_callback(
                    f"Đang viết chương {outline.chapter_number}: {outline.title}..."
                )

            # Build chapter contract (unified per-chapter requirements)
            contract, contract_text = build_contract_for_chapter(
                self.config,
                outline,
                threads=list(story_context.open_threads),
                macro_arcs=macro_arcs,
                conflicts=conflict_web,
                foreshadowing_plan=foreshadowing_plan,
                characters=characters,
                draft=draft,
                previous_failures=_contract_failures,
                include_proactive=True,
            )

            # Build enhancement context (theme, voice, scenes, show-don't-tell)
            # plus optional injections (threads, causal, memories, foreshadowing)
            enhancement_context = build_chapter_enhancement_context(
                self.config,
                self.llm,
                genre=genre,
                pacing=pacing,
                premise=premise,
                voice_profiles=voice_profiles,
                outline=outline,
                characters=characters,
                world=world,
                story_context=story_context,
                foreshadowing_plan=foreshadowing_plan,
                layer_model=self.gen._layer_model,
                progress_callback=progress_callback,
            )

            # Scene beats, optional decomposition, optional per-beat writing
            enhancement_context, chapter_scenes, _beat_chapter = (
                prepare_scene_context_and_beat_chapter(
                    self,
                    outline=outline,
                    characters=characters,
                    world=world,
                    genre=genre,
                    title=title,
                    style=style,
                    word_count=word_count,
                    story_context=story_context,
                    enhancement_context=enhancement_context,
                    stream_callback=stream_callback,
                    idea=idea,
                    idea_summary=idea_summary,
                )
            )

            chapter = write_sequential_chapter(
                self,
                outline=outline,
                contract=contract,
                contract_text=contract_text,
                beat_chapter=_beat_chapter,
                stream_callback=stream_callback,
                title=title,
                genre=genre,
                style=style,
                characters=characters,
                world=world,
                word_count=word_count,
                story_context=story_context,
                all_chapter_texts=all_chapter_texts,
                bible_ctx=bible_ctx,
                active_conflicts=active_conflicts,
                seeds=seeds,
                payoffs=payoffs,
                pacing=pacing,
                enhancement_context=enhancement_context,
                arc_context=arc_context,
                chapter_scenes=chapter_scenes,
                idea=idea,
                idea_summary=idea_summary,
            )

            chapters.append(chapter)
            all_chapter_texts.append(chapter.content)

            # Sprint 2 Task 1: auto-index chapter into semantic RAG
            _index_chapter_into_rag(
                self.config,
                chapter,
                outline,
                characters,
                list(story_context.open_threads) if story_context else None,
            )

            if progress_callback:
                progress_callback(
                    f"Đang trích xuất context chương {outline.chapter_number}..."
                )

            # --- Enhancement 6: Chapter self-critique ---
            run_chapter_self_critique(
                self.config.pipeline,
                self.llm,
                chapter=chapter,
                outline=outline,
                characters=characters,
                genre=genre,
                pacing=pacing,
                macro_arcs=macro_arcs,
                story_context=story_context,
                draft=draft,
                layer_model=self.gen._layer_model,
                progress_callback=progress_callback,
            )

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
                open_threads=list(story_context.open_threads),
                foreshadowing_plan=foreshadowing_plan,
                layer_model=self.gen._layer_model,
            )

            # Post-write contract validation with retry (#2 improvement)
            _contract_failures = validate_and_retry_contract(
                self.gen,
                self.config.pipeline,
                self.llm,
                retry_max=self.retry_max,
                retry_threshold=self.retry_threshold,
                chapter=chapter,
                outline=outline,
                contract=contract,
                contract_text=contract_text,
                chapters=chapters,
                all_chapter_texts=all_chapter_texts,
                story_context=story_context,
                bible_ctx=bible_ctx,
                active_conflicts=active_conflicts,
                seeds=seeds,
                payoffs=payoffs,
                pacing=pacing,
                enhancement_context=enhancement_context,
                arc_context=arc_context,
                chapter_scenes=chapter_scenes,
                stream_callback=stream_callback,
                title=title,
                genre=genre,
                style=style,
                characters=characters,
                world=world,
                word_count=word_count,
                macro_arcs=macro_arcs,
                conflict_web=conflict_web,
                foreshadowing_plan=foreshadowing_plan,
                previous_failures=_contract_failures,
                progress_callback=progress_callback,
                idea=idea,
                idea_summary=idea_summary,
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

    async def _run_batch_async(
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
        """Async batch execution using asyncio.gather() (#1 improvement)."""
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

        # Causal accumulator for cross-chapter sync (#3 improvement)
        causal_acc = CausalAccumulator() if self.causal_sync else None

        async def _write_one_async(
            outline: ChapterOutline,
        ) -> tuple[Chapter, dict | None]:
            """Write single chapter in thread pool, return chapter + contract for retry.

            P0-8: Each coroutine runs inside its own copy_context() so set_chapter/
            set_module mutations inside the threaded worker cannot leak across
            sibling tasks within asyncio.gather().
            """
            import contextvars
            from services.trace_context import set_chapter, set_module

            ctx = contextvars.copy_context()

            def _runner():
                # Pin chapter+module on this isolated context BEFORE the threaded
                # write so all LLM calls record under the correct chapter even if
                # the worker forgets to set them.
                set_chapter(outline.chapter_number)
                set_module("chapter_writer")
                return self._write_chapter_parallel(
                    outline,
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
                )

            return await asyncio.to_thread(ctx.run, _runner)

        # Execute all chapters concurrently
        if progress_callback:
            progress_callback(f"[ASYNC] Đang viết {len(batch)} chương song song...")

        results = await asyncio.gather(
            *[_write_one_async(o) for o in batch],
            return_exceptions=True,
        )

        # Process results, handle errors — collect successes first, then re-raise
        chapters = []
        contracts = {}
        first_exc: Exception | None = None
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    "Async write failed for chapter %d: %s",
                    batch[i].chapter_number,
                    result,
                )
                if first_exc is None:
                    first_exc = result
            else:
                chapter, contract = result
                chapters.append(chapter)
                if contract:
                    contracts[chapter.chapter_number] = contract

        # Sprint 2 Task 1: serial-index post-gather to avoid ChromaDB write contention
        for ch in chapters:
            outline_for_ch = next(
                (o for o in batch if o.chapter_number == ch.chapter_number), None
            )
            if outline_for_ch is None:
                continue
            _index_chapter_into_rag(
                self.config,
                ch,
                outline_for_ch,
                characters,
                list(frozen_threads) if frozen_threads else None,
            )

        # Re-raise after persisting successes so completed work isn't lost
        if first_exc is not None:
            if chapters:
                logger.warning(
                    "Batch partial failure: %d chapter(s) succeeded before error; re-raising.",
                    len(chapters),
                )
            raise first_exc

        # Contract validation with retry (#2 improvement) — the shared helper
        # gates on contracts + enable_contract_validation itself; the whole
        # sequential loop runs in one worker thread so the event loop stays free.
        chapters = await asyncio.to_thread(
            validate_and_retry_threaded,
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

        # Causal sync: merge accumulated events into story_context (#3 improvement)
        if causal_acc and self.causal_sync:
            self._sync_causal_events(causal_acc, story_context, progress_callback)

        if progress_callback:
            progress_callback(
                f"[BATCH] {len(chapters_ordered)} chương viết xong, đang trích xuất context..."
            )

        # Post-processing — P1-2: parallelize across chapters via asyncio.gather.
        # Each chapter's 4-call pipeline runs sequentially within its coroutine,
        # but coroutines run concurrently. A threading.RLock on story_context
        # serializes the shared-state mutations done inside the post-write
        # functions (recent_summaries, character_states, plot_events,
        # foreshadowing_payoff_missing, consistency flags).
        sorted_pairs = list(
            zip(sorted(batch, key=lambda o: o.chapter_number), chapters_ordered)
        )
        # Append chapter texts up-front (order-preserving) so siblings see them.
        for _, ch in sorted_pairs:
            all_chapter_texts.append(ch.content)

        # Post-write must be serial: finalize_chapter does in-order in-place
        # mutations to shared story_context (recent_summaries, character_states,
        # plot_events, foreshadowing_payoff_missing) that later steps in the same
        # call read. A previous version of this code wrapped finalize_chapter in
        # an RLock and called it via asyncio.gather → fully serialized anyway,
        # plus added thread-pool overhead. Run-as-loop is the honest version.
        for outline, chapter in sorted_pairs:
            await asyncio.to_thread(
                finalize_chapter,
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

    def _write_chapter_parallel(
        self,
        outline: ChapterOutline,
        frozen: FrozenContext,
        draft: StoryDraft,
        story_context: StoryContext,
        frozen_threads: list,
        sibling_summaries: str,
        shared_enhancement: str,
        title: str,
        genre: str,
        style: str,
        characters: list,
        world,
        word_count: int,
        macro_arcs,
        conflict_web,
        foreshadowing_plan,
        progress_callback,
        causal_acc: CausalAccumulator | None,
        idea: str = "",
        idea_summary: str = "",
        override_contract=None,
    ) -> tuple[Chapter, dict | None]:
        """Write a single chapter for parallel execution. Returns (chapter, contract)."""
        try:
            from services.trace_context import set_chapter, set_module

            set_chapter(outline.chapter_number)
            set_module("chapter_writer")
        except Exception:
            pass
        (
            bible_ctx,
            frozen_ctx,
            active_conflicts,
            seeds,
            payoffs,
            pacing,
            arc_context,
            per_chapter_enhancement,
        ) = assemble_parallel_write_inputs(
            self.gen,
            self.config,
            self.llm,
            outline=outline,
            frozen=frozen,
            draft=draft,
            story_context=story_context,
            frozen_threads=frozen_threads,
            sibling_summaries=sibling_summaries,
            shared_enhancement=shared_enhancement,
            characters=characters,
            world=world,
            genre=genre,
            macro_arcs=macro_arcs,
            conflict_web=conflict_web,
            foreshadowing_plan=foreshadowing_plan,
        )

        # Contract
        p_contract, p_contract_text = build_contract_for_chapter(
            self.config,
            outline,
            threads=frozen_threads,
            macro_arcs=macro_arcs,
            conflicts=conflict_web,
            foreshadowing_plan=foreshadowing_plan,
            characters=characters,
            override_contract=override_contract,
        )

        if progress_callback:
            progress_callback(
                f"Đang viết chương {outline.chapter_number}: {outline.title}..."
            )

        _p_negotiated = p_contract.to_negotiated() if p_contract is not None else None
        ch_result = self.gen._write_chapter_with_long_context(
            title,
            genre,
            style,
            characters,
            world,
            outline,
            word_count,
            frozen_ctx,
            list(frozen.chapter_texts),
            bible_ctx,
            open_threads=frozen_threads,
            active_conflicts=active_conflicts,
            foreshadowing_to_plant=seeds,
            foreshadowing_to_payoff=payoffs,
            pacing_type=pacing,
            enhancement_context=per_chapter_enhancement,
            current_arc_context=arc_context,
            chapter_contract=p_contract_text,
            negotiated_contract=_p_negotiated,
            idea=idea,
            idea_summary=idea_summary,
        )

        if p_contract is not None:
            try:
                ch_result.contract = p_contract
                object.__setattr__(
                    ch_result, "negotiated_contract", p_contract.to_negotiated()
                )
            except Exception:
                pass

        # Causal event extraction (#3 improvement)
        if causal_acc:
            self._extract_causal_events(ch_result, outline, causal_acc)

        return ch_result, p_contract

    def _extract_causal_events(
        self,
        chapter: Chapter,
        outline: ChapterOutline,
        causal_acc: CausalAccumulator,
    ):
        """Extract causal events from chapter for cross-batch sync."""
        try:
            # Simple heuristic: extract key plot points from content
            # More sophisticated: use LLM to identify cause-effect chains
            keywords = ["vì thế", "do đó", "kết quả", "dẫn đến", "bởi vì", "nên"]
            content_lower = chapter.content.lower()
            for kw in keywords:
                if kw in content_lower:
                    causal_acc.add_event(
                        chapter_num=outline.chapter_number,
                        event_type="causal_marker",
                        description=f"Chapter {outline.chapter_number} contains causal keyword: {kw}",
                    )
                    break
        except Exception as e:
            logger.debug(
                "Causal extraction failed for ch%d: %s", outline.chapter_number, e
            )

    def _sync_causal_events(
        self,
        causal_acc: CausalAccumulator,
        story_context: StoryContext,
        progress_callback,
    ):
        """Sync accumulated causal events back to story_context."""
        events = causal_acc.get_events_sorted()
        if not events:
            return

        # Merge into story_context.plot_events or a dedicated causal_graph
        causal_graph = getattr(story_context, "causal_graph", None)
        if causal_graph and hasattr(causal_graph, "add_event"):
            for ev in events:
                try:
                    causal_graph.add_event(
                        chapter=ev["chapter"],
                        event_type=ev["type"],
                        description=ev["description"],
                    )
                except Exception:
                    pass

        if progress_callback and events:
            progress_callback(
                f"[CAUSAL] Synced {len(events)} causal events from parallel batch"
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

    @staticmethod
    def _build_sibling_context(batch: list[ChapterOutline]) -> str:
        """Build sibling outline context for parallel chapters to avoid duplication."""
        if len(batch) <= 1:
            return ""
        lines = []
        for o in batch:
            lines.append(f"- Ch{o.chapter_number}: {o.title} — {o.summary}")
        return "\n".join(lines)
