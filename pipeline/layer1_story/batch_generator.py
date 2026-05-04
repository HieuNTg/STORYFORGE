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
from pipeline.layer1_story.post_processing import process_chapter_post_write
from pipeline.layer1_story.context_helpers import get_rag_batch_cache
from services.token_counter import estimate_tokens

logger = logging.getLogger(__name__)


@dataclass
class CausalAccumulator:
    """Thread-safe accumulator for causal events across parallel chapters.

    Used to sync causal graph updates after parallel batch completes.
    """
    events: list[dict] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def add_event(self, chapter_num: int, event_type: str, description: str,
                  causes: list[int] = None, effects: list[int] = None):
        with self._lock:
            self.events.append({
                "chapter": chapter_num,
                "type": event_type,
                "description": description,
                "causes": causes or [],
                "effects": effects or [],
            })

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


def _rewrite_for_consistency_violations(
    pipeline_config,
    llm,
    chapter: Chapter,
    outline: ChapterOutline,
    story_context: StoryContext,
    layer_model: str | None,
    progress_callback: Callable | None = None,
) -> None:
    """L1-D: Rewrite chapter when consistency validators flagged violations above threshold.

    Reads name_warnings / arc_drift_warnings from story_context + location warnings
    stashed on story_context.world_rule_violations. Mutates chapter.content in place.
    """
    if not getattr(pipeline_config, "enable_consistency_rewrite", False):
        return

    name_threshold = int(getattr(pipeline_config, "consistency_name_warning_threshold", 3))
    arc_threshold = int(getattr(pipeline_config, "consistency_arc_drift_threshold", 2))
    loc_threshold = int(getattr(pipeline_config, "consistency_location_warning_threshold", 2))

    issues: list[str] = []
    name_warnings = list(story_context.name_warnings or [])
    arc_warnings = list(story_context.arc_drift_warnings or [])
    # Location warnings may live in world_rule_violations — filter by prefix
    loc_warnings = [w for w in (story_context.world_rule_violations or []) if w.startswith("[VỊ TRÍ]")]

    trigger = (
        len(name_warnings) >= name_threshold
        or len(arc_warnings) >= arc_threshold
        or len(loc_warnings) >= loc_threshold
    )
    if not trigger:
        return

    issues.extend(name_warnings)
    issues.extend(arc_warnings)
    issues.extend(loc_warnings)

    try:
        from pipeline.layer1_story.chapter_self_critique import rewrite_for_consistency
        from models.schemas import count_words

        if progress_callback:
            progress_callback(
                f"Ch{outline.chapter_number}: viết lại để sửa {len(issues)} lỗi nhất quán..."
            )
        revised = rewrite_for_consistency(llm, chapter.content, issues, model=layer_model)
        if not revised or revised == chapter.content:
            return
        chapter.content = revised
        chapter.word_count = count_words(revised)
        # Clear warnings — they were based on the now-discarded content.
        # Keep loc_warnings from world_rule_violations untouched (may include non-location rules)
        story_context.name_warnings = []
        story_context.arc_drift_warnings = []
        if loc_warnings:
            story_context.world_rule_violations = [
                w for w in story_context.world_rule_violations if not w.startswith("[VỊ TRÍ]")
            ]
        if progress_callback:
            progress_callback(f"Ch{outline.chapter_number}: đã viết lại (consistency)")
    except Exception as e:
        logger.warning(
            "Consistency rewrite failed for ch%d (non-fatal): %s",
            outline.chapter_number, e,
        )


def _enforce_pacing(
    pipeline_config,
    llm,
    chapter: Chapter,
    outline: ChapterOutline,
    layer_model: str | None,
    progress_callback: Callable | None = None,
) -> None:
    """L1-F: Classify chapter pacing; if confident mismatch, rewrite.

    Mutates chapter.content/word_count in place. Non-fatal.
    """
    if not getattr(pipeline_config, "enable_pacing_enforcement", False):
        return
    target = (getattr(outline, "pacing_type", "") or "").strip().lower()
    if not target:
        return
    try:
        from pipeline.layer1_story.pacing_enforcer import verify_pacing, rewrite_for_pacing
        from models.schemas import count_words

        verdict = verify_pacing(llm, chapter.content, target, model=layer_model)
        if not verdict or verdict.get("match", True):
            return
        conf_threshold = float(getattr(pipeline_config, "pacing_enforcement_confidence", 0.7))
        if float(verdict.get("confidence", 0.0)) < conf_threshold:
            logger.debug(
                "Ch%d pacing mismatch under threshold (target=%s, detected=%s, conf=%.2f)",
                outline.chapter_number, target, verdict.get("detected"), verdict.get("confidence", 0.0),
            )
            return
        if not getattr(pipeline_config, "pacing_mismatch_rewrite", False):
            if progress_callback:
                progress_callback(
                    f"⚠️ Ch{outline.chapter_number} pacing lệch "
                    f"(muốn {target}, thực {verdict.get('detected')}) — không rewrite"
                )
            return
        if progress_callback:
            progress_callback(
                f"Ch{outline.chapter_number}: viết lại cho khớp nhịp '{target}'..."
            )
        revised = rewrite_for_pacing(
            llm, chapter.content, target,
            verdict.get("detected", ""), verdict.get("reason", ""),
            model=layer_model,
        )
        if revised and revised != chapter.content:
            chapter.content = revised
            chapter.word_count = count_words(revised)
            if progress_callback:
                progress_callback(f"Ch{outline.chapter_number}: đã viết lại (pacing)")
    except Exception as e:
        logger.warning(
            "Pacing enforcement failed for ch%d (non-fatal): %s",
            outline.chapter_number, e,
        )


def _verify_and_rewrite_missing_payoffs(
    pipeline_config,
    llm,
    chapter: Chapter,
    outline: ChapterOutline,
    story_context: StoryContext,
    foreshadowing_plan: list | None,
    layer_model: str | None,
    progress_callback: Callable | None = None,
) -> None:
    """L1-E: Targeted rewrite when post_processing flagged missing payoffs.

    Mutates chapter.content + story_context.foreshadowing_payoff_missing in place.
    Gated by pipeline_config.foreshadowing_payoff_rewrite_on_miss.
    """
    if not getattr(pipeline_config, "foreshadowing_payoff_rewrite_on_miss", False):
        return
    if not story_context.foreshadowing_payoff_missing:
        return

    try:
        from pipeline.layer1_story.chapter_self_critique import rewrite_for_missing_payoffs
        from pipeline.layer1_story.foreshadowing_manager import get_payoffs_due
        from pipeline.semantic.foreshadowing_verifier import verify_payoffs
        from models.schemas import count_words

        missing = list(story_context.foreshadowing_payoff_missing)
        if progress_callback:
            progress_callback(
                f"Ch{outline.chapter_number}: viết lại để thực hiện {len(missing)} payoff..."
            )
        revised = rewrite_for_missing_payoffs(
            llm, chapter.content, missing, model=layer_model,
        )
        if not revised or revised == chapter.content:
            return

        chapter.content = revised
        chapter.word_count = count_words(revised)

        # Re-verify against rewritten content (embedding-based, no LLM call)
        due_after = get_payoffs_due(foreshadowing_plan or [], outline.chapter_number)
        if due_after:
            threshold = float(getattr(pipeline_config, "semantic_payoff_threshold", 0.62))
            verify_payoffs(due_after, [chapter], threshold=threshold)
            still_missing = [p for p in due_after if not p.paid_off]
            story_context.foreshadowing_payoff_missing = [
                {
                    "hint": p.hint,
                    "confidence": p.planted_confidence or 0.0,
                    "payoff_chapter": p.payoff_chapter,
                    "plant_chapter": p.plant_chapter,
                }
                for p in still_missing
            ]
            if still_missing and progress_callback:
                progress_callback(
                    f"⚠️ Ch{outline.chapter_number}: {len(still_missing)} payoff "
                    f"vẫn chưa đạt ngưỡng sau rewrite"
                )
    except Exception as e:
        logger.warning(
            "Payoff rewrite failed for ch%d (non-fatal): %s",
            outline.chapter_number, e,
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
            chars = [getattr(c, "name", "") for c in (characters or []) if getattr(c, "name", "")]
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
        logger.debug(f"RAG index failed for ch{chapter.chapter_number} (non-fatal): {e}")
        return 0


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
        self.use_asyncio = getattr(self.config.pipeline, "parallel_use_asyncio", True)
        self.retry_max = getattr(self.config.pipeline, "chapter_retry_max", 2)
        self.retry_threshold = getattr(self.config.pipeline, "chapter_retry_threshold", 0.6)
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
        resume_from_batch: int = 0,
        # NEW:
        macro_arcs=None,
        conflict_web=None,
        foreshadowing_plan=None,
        premise=None,
        voice_profiles=None,
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
        mode = "parallel" if self.parallel_enabled else "sequential"
        _log(f"[BATCH] {len(outlines)} chương / {len(batches)} batch (size={self.batch_size}, mode={mode})")

        if resume_from_batch > 0:
            _log(f"[BATCH] Resuming from batch {resume_from_batch + 1}")

        with ThreadPoolExecutor(max_workers=3) as executor:
            for batch_idx, batch in enumerate(batches):
                if batch_idx < resume_from_batch:
                    continue

                frozen = FrozenContext(story_context, all_chapter_texts)
                # Bug #4: Reset RAG cache at batch boundary
                get_rag_batch_cache().reset_batch()
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

                        executor=executor,
                        self_reviewer=self_reviewer,
                        progress_callback=progress_callback,
                        macro_arcs=macro_arcs,
                        conflict_web=conflict_web,
                        foreshadowing_plan=foreshadowing_plan,
                        premise=premise,
                        voice_profiles=voice_profiles,
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
                    )

                for ch in batch_chapters:
                    draft.chapters.append(ch)

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
        recent_chapters = sorted({e.chapter_number for e in story_context.extraction_health[-60:]})[-3:]
        if len(recent_chapters) < 3:
            return
        bad_chapters = sum(
            1 for ch in recent_chapters
            if len(story_context.failed_extractions_in_last_chapter(ch)) >= 3
        )
        if bad_chapters >= 3:
            raise RuntimeError(
                f"Context corruption detected: 3 consecutive chapters ({recent_chapters}) "
                f"with >=3 extraction failures each. Health score: {score:.0%}. "
                f"Pipeline halted to prevent building on corrupted state. "
                f"Check LLM connectivity / rate limits / API key."
            )

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

        executor: ThreadPoolExecutor,
        self_reviewer,
        progress_callback,
        stream_callback,
        macro_arcs=None,
        conflict_web=None,
        foreshadowing_plan=None,
        premise=None,
        voice_profiles=None,
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

            bible_ctx = ""
            if draft.story_bible:
                bible_ctx = self.gen.bible_manager.get_context_for_chapter(
                    draft.story_bible,
                    outline.chapter_number,
                    recent_summaries=list(story_context.recent_summaries),
                    character_states=list(story_context.character_states),
                )

            # Tiered context: replaces flat bible_ctx with priority-based 4-tier system
            if getattr(self.config.pipeline, "enable_tiered_context", False):
                try:
                    from pipeline.layer1_story.tiered_context_builder import (
                        build_tiered_context, build_compressed_context, should_use_compressed_context,
                    )
                    # Emotional bridge: pass prev_chapter if enabled
                    prev_ch = None
                    if getattr(self.config.pipeline, "enable_emotional_bridge", False):
                        prev_ch = draft.chapters[-1] if draft.chapters else None

                    # Use compressed context for long stories (20+ chapters)
                    total_chs = len(draft.chapters) + len([o for o in batch if o.chapter_number > len(draft.chapters)])
                    if should_use_compressed_context(total_chs, threshold=20):
                        tiered = build_compressed_context(
                            chapter_num=outline.chapter_number,
                            chapters=draft.chapters,
                            outline=outline,
                            macro_arcs=macro_arcs,
                            open_threads=list(story_context.open_threads),
                            story_bible=draft.story_bible,
                            all_chapter_texts=all_chapter_texts,
                            max_tokens=getattr(self.config.pipeline, "tiered_context_max_tokens", 4000),
                            prev_chapter=prev_ch,
                        )
                    else:
                        tiered = build_tiered_context(
                            chapter_num=outline.chapter_number,
                            chapters=draft.chapters,
                            outline=outline,
                            open_threads=list(story_context.open_threads),
                            story_bible=draft.story_bible,
                            all_chapter_texts=all_chapter_texts,
                            max_tokens=getattr(self.config.pipeline, "tiered_context_max_tokens", 3000),
                            max_promotions=getattr(self.config.pipeline, "tiered_max_promotions", 5),
                            prev_chapter=prev_ch,
                        )
                    if tiered:
                        bible_ctx = tiered
                except Exception as e:
                    logger.warning("Tiered context failed for ch%d (using bible fallback): %s", outline.chapter_number, e)

            # Resolve per-chapter narrative context
            active_conflicts = []
            seeds = []
            payoffs = []
            pacing = ""
            current_arc = None
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

            # Build arc context string for chapter writing prompt (Fix #11)
            arc_context = ""
            if current_arc:
                arc_context = (
                    f"Arc {current_arc.arc_number}: {current_arc.name}\n"
                    f"Xung đột trung tâm: {current_arc.central_conflict}\n"
                    f"Nhân vật trọng tâm: {', '.join(current_arc.character_focus) if current_arc.character_focus else 'tất cả'}\n"
                    f"Kết thúc arc: {current_arc.resolution}\n"
                    f"Cung bậc cảm xúc: {current_arc.emotional_trajectory}"
                )

            if progress_callback:
                progress_callback(
                    f"Đang viết chương {outline.chapter_number}: {outline.title}..."
                )

            # Build chapter contract (unified per-chapter requirements)
            contract_text = ""
            contract = None
            if getattr(self.config.pipeline, "enable_chapter_contracts", False):
                try:
                    from pipeline.layer1_story.chapter_contract_builder import build_contract, format_contract_for_prompt
                    # Proactive constraints: pass world_rules and character_secrets
                    contract_world_rules = None
                    contract_secrets = None
                    if getattr(self.config.pipeline, "enable_proactive_constraints", False):
                        contract_world_rules = getattr(draft.world, 'rules', None) or []
                        contract_secrets = {
                            c.name: getattr(c, 'secret', '')
                            for c in characters
                            if hasattr(c, 'secret') and getattr(c, 'secret', '')
                        }
                    contract = build_contract(
                        outline.chapter_number, outline,
                        threads=list(story_context.open_threads),
                        macro_arcs=macro_arcs,
                        conflicts=conflict_web,
                        foreshadowing_plan=foreshadowing_plan,
                        characters=characters,
                        previous_failures=_contract_failures,
                        world_rules=contract_world_rules,
                        character_secrets=contract_secrets,
                    )
                    contract_text = format_contract_for_prompt(contract)
                except Exception as e:
                    logger.warning("Contract build failed for ch%d (non-fatal): %s", outline.chapter_number, e)

            # Build enhancement context (theme, voice, scenes, show-don't-tell)
            from pipeline.layer1_story.enhancement_context_builder import build_enhancement_context
            enhancement_context = build_enhancement_context(
                self.config, self.llm, genre, pacing,
                premise=premise, voice_profiles=voice_profiles,
                outline=outline, characters=characters, world=world,
                layer_model=self.gen._layer_model,
            )

            # Thread enforcement: inject mandatory threads as hard requirement
            if getattr(self.config.pipeline, "enable_thread_enforcement", False):
                try:
                    from pipeline.layer1_story.plot_thread_tracker import format_mandatory_threads
                    mandatory = format_mandatory_threads(
                        list(story_context.open_threads), outline.chapter_number, gap_threshold=8,
                    )
                    if mandatory:
                        enhancement_context = f"{enhancement_context}\n\n{mandatory}" if enhancement_context else mandatory
                except Exception as e:
                    logger.debug("Thread enforcement failed (non-fatal): %s", e)

            # Causal dependencies injection
            if getattr(self.config.pipeline, "enable_l1_causal_graph", False):
                try:
                    from pipeline.layer1_story.l1_causal_graph import format_causal_dependencies_for_prompt
                    causal_graph = getattr(story_context, "causal_graph", None)
                    if causal_graph:
                        required = causal_graph.query_required_references(outline.chapter_number, min_age=2)
                        causal_block = format_causal_dependencies_for_prompt(required)
                        if causal_block:
                            enhancement_context = f"{enhancement_context}\n\n{causal_block}" if enhancement_context else causal_block
                except Exception as e:
                    logger.debug("Causal dependencies injection failed (non-fatal): %s", e)

            # Emotional memory injection
            if getattr(self.config.pipeline, "enable_emotional_memory", False):
                try:
                    from pipeline.layer1_story.character_memory_bank import format_memories_for_prompt
                    banks = getattr(story_context, "emotional_memory_banks", None) or {}
                    if banks:
                        memories_block = format_memories_for_prompt(banks, last_n=3)
                        if memories_block and memories_block != "Không có ký ức cảm xúc.":
                            enhancement_context = f"{enhancement_context}\n\n## KÝ ỨC CẢM XÚC NHÂN VẬT:\n{memories_block}"
                except Exception as e:
                    logger.debug("Emotional memory injection failed (non-fatal): %s", e)

            # Bug #5: Inject foreshadowing status summary
            if foreshadowing_plan:
                try:
                    from pipeline.layer1_story.foreshadowing_manager import get_foreshadowing_status
                    foreshadowing_status = get_foreshadowing_status(foreshadowing_plan, outline.chapter_number)
                    if foreshadowing_status:
                        enhancement_context = f"{enhancement_context}\n\n{foreshadowing_status}" if enhancement_context else foreshadowing_status
                except Exception as e:
                    logger.debug("Foreshadowing status injection failed (non-fatal): %s", e)

            # Foreshadowing payoff enforcement (Phase 6)
            if foreshadowing_plan and getattr(self.config.pipeline, "enable_foreshadowing_enforcement", True):
                try:
                    from pipeline.layer1_story.foreshadowing_manager import (
                        get_overdue_payoffs, get_approaching_payoffs,
                        format_payoff_enforcement_prompt,
                    )
                    overdue = get_overdue_payoffs(foreshadowing_plan, outline.chapter_number, grace_chapters=2)
                    approaching = get_approaching_payoffs(foreshadowing_plan, outline.chapter_number, lookahead=3)
                    if overdue or approaching:
                        payoff_block = format_payoff_enforcement_prompt(
                            overdue, approaching, outline.chapter_number,
                        )
                        if payoff_block:
                            enhancement_context = f"{enhancement_context}\n\n{payoff_block}" if enhancement_context else payoff_block
                            if overdue and progress_callback:
                                progress_callback(f"⚠️ {len(overdue)} foreshadowing quá hạn cần payoff")
                except Exception as e:
                    logger.debug("Foreshadowing payoff enforcement failed (non-fatal): %s", e)

            # Append scene beats for climax/twist chapters (Fix #12)
            from pipeline.layer1_story.scene_beat_generator import generate_scene_beats, format_beats_for_prompt
            scene_beats_list = generate_scene_beats(
                self.llm, outline, characters, world, genre,
                model_tier=self.gen._layer_model or "cheap",
            )
            scene_beats_text = ""
            if scene_beats_list:
                scene_beats_text = format_beats_for_prompt(scene_beats_list)
                enhancement_context = f"{enhancement_context}\n\n{scene_beats_text}" if enhancement_context else scene_beats_text

            # Scene decomposition: decompose chapter into 3-5 scenes before writing
            chapter_scenes: list[dict] = []
            if getattr(self.config.pipeline, "enable_scene_decomposition", False):
                try:
                    from pipeline.layer1_story.scene_decomposer import decompose_chapter_scenes
                    chapter_scenes = decompose_chapter_scenes(
                        self.llm, outline, characters, world, genre,
                        model=self.gen._layer_model,
                    )
                except Exception as e:
                    logger.warning("Scene decomposition failed for ch%d (non-fatal): %s", outline.chapter_number, e)

            # Scene beat writing: per-beat generation when enabled
            use_beat_writing = (
                getattr(self.config.pipeline, "enable_scene_beat_writing", False)
                and scene_beats_list
                and not stream_callback  # stream mode not compatible
            )

            if use_beat_writing:
                try:
                    from pipeline.layer1_story.chapter_writer import write_chapter_by_beats
                    beat_context = {
                        "previous_summary": "\n".join(story_context.recent_summaries[-2:]),
                        "characters_text": ", ".join(c.name for c in characters[:5]),
                        "world_text": getattr(world, 'setting', '') if world else "",
                    }
                    chapter_content = write_chapter_by_beats(
                        self.llm, scene_beats_list, beat_context,
                        title, genre, style, word_count,
                        model=self.gen._layer_model,
                    )
                    from models.schemas import count_words
                    chapter = Chapter(
                        chapter_number=outline.chapter_number,
                        title=outline.title,
                        content=chapter_content,
                        word_count=count_words(chapter_content),
                    )
                except Exception as e:
                    logger.warning("Beat writing failed for ch%d, falling back: %s", outline.chapter_number, e)
                    use_beat_writing = False

            if not use_beat_writing and stream_callback:
                chapter = self.gen.write_chapter_stream(
                    title, genre, style, characters, world, outline,
                    word_count=word_count, context=story_context,
                    stream_callback=stream_callback,
                    open_threads=list(story_context.open_threads),
                    active_conflicts=active_conflicts,
                    foreshadowing_to_plant=seeds,
                    foreshadowing_to_payoff=payoffs,
                    pacing_type=pacing,
                    enhancement_context=enhancement_context,
                    current_arc_context=arc_context,
                    chapter_contract=contract_text,
                    scenes=chapter_scenes,
                )
            elif not use_beat_writing:
                chapter = self.gen._write_chapter_with_long_context(
                    title, genre, style, characters, world, outline,
                    word_count, story_context, all_chapter_texts, bible_ctx,
                    open_threads=list(story_context.open_threads),
                    active_conflicts=active_conflicts,
                    foreshadowing_to_plant=seeds,
                    foreshadowing_to_payoff=payoffs,
                    pacing_type=pacing,
                    enhancement_context=enhancement_context,
                    current_arc_context=arc_context,
                    chapter_contract=contract_text,
                    scenes=chapter_scenes,
                )

            if contract is not None:
                try:
                    chapter.contract = contract
                    # Sprint 1 P5: stash unified NegotiatedChapterContract on the
                    # chapter as an in-memory attribute (DB column lands in P6).
                    object.__setattr__(chapter, "negotiated_contract", contract.to_negotiated())
                except Exception as e:
                    logger.debug("Attach contract to chapter failed: %s", e)

            chapter_tokens_used = estimate_tokens(chapter.content)
            usage_pct = (chapter_tokens_used / self.gen.token_budget_per_chapter) * 100
            if usage_pct >= 80:
                logger.warning(
                    "Chapter %d at %d%% of token budget (%d/%d estimated tokens)",
                    outline.chapter_number, int(usage_pct),
                    chapter_tokens_used, self.gen.token_budget_per_chapter,
                )

            chapters.append(chapter)
            all_chapter_texts.append(chapter.content)

            # Sprint 2 Task 1: auto-index chapter into semantic RAG
            _index_chapter_into_rag(
                self.config, chapter, outline, characters,
                list(story_context.open_threads) if story_context else None,
            )

            if progress_callback:
                progress_callback(
                    f"Đang trích xuất context chương {outline.chapter_number}..."
                )

            # --- Enhancement 6: Chapter self-critique ---
            if self.config.pipeline.enable_chapter_critique:
                try:
                    from pipeline.layer1_story.chapter_self_critique import (
                        critique_chapter, rewrite_weak_sections, should_critique,
                        aggregate_critique_score,
                    )
                    every_n = int(getattr(self.config.pipeline, "chapter_critique_every_n_chapters", 0) or 0)
                    if should_critique(outline.chapter_number, story_context.total_chapters,
                                       macro_arcs=macro_arcs, pacing_type=pacing,
                                       every_n_chapters=every_n):
                        outline_text = f"{outline.title}: {outline.summary}"
                        crit = critique_chapter(
                            self.llm, chapter.content, outline_text,
                            characters, genre, pacing, model=self.gen._layer_model,
                        )
                        if crit:
                            original_content = chapter.content
                            score_before = aggregate_critique_score(crit)
                            revised = rewrite_weak_sections(
                                self.llm, chapter.content, crit,
                                model=self.gen._layer_model,
                            )
                            if revised != original_content:
                                from models.schemas import count_words
                                chapter.content = revised
                                chapter.word_count = count_words(revised)
                                # L1-B rollback: re-score revised; revert if aggregate drops.
                                if getattr(self.config.pipeline, "chapter_critique_rollback", False):
                                    try:
                                        crit_after = critique_chapter(
                                            self.llm, revised, outline_text,
                                            characters, genre, pacing, model=self.gen._layer_model,
                                        )
                                        score_after = aggregate_critique_score(crit_after) if crit_after else score_before
                                        threshold = float(getattr(
                                            self.config.pipeline, "chapter_critique_rollback_threshold", 0.3
                                        ))
                                        if score_after + threshold < score_before:
                                            chapter.content = original_content
                                            chapter.word_count = count_words(original_content)
                                            if progress_callback:
                                                progress_callback(
                                                    f"⚠️ Ch{outline.chapter_number} rollback self-critique "
                                                    f"({score_before:.2f} → {score_after:.2f})"
                                                )
                                            logger.info(
                                                "Ch%d critique rollback: %.2f → %.2f",
                                                outline.chapter_number, score_before, score_after,
                                            )
                                        elif progress_callback:
                                            progress_callback(
                                                f"Chương {outline.chapter_number} cải thiện "
                                                f"({score_before:.2f} → {score_after:.2f})"
                                            )
                                    except Exception as e:
                                        logger.debug("Rollback rescore failed (keeping revised): %s", e)
                                elif progress_callback:
                                    progress_callback(f"Chương {outline.chapter_number} đã cải thiện qua self-critique")
                except Exception as e:
                    logger.warning("Chapter self-critique failed for ch%d (non-fatal): %s", outline.chapter_number, e)

            process_chapter_post_write(
                chapter, outline, story_context, characters, context_window,
                executor, self.llm, draft, self.gen.bible_manager,
                progress_callback, genre, word_count,
                self.config.pipeline.enable_self_review, self_reviewer,
                open_threads=list(story_context.open_threads),
                foreshadowing_plan=foreshadowing_plan,
                world_rules=getattr(draft.world, 'rules', None) or [],
                voice_profiles=getattr(draft, 'voice_profiles', None) or [],
                pipeline_config=self.config.pipeline,
            )

            _verify_and_rewrite_missing_payoffs(
                self.config.pipeline, self.llm, chapter, outline,
                story_context, foreshadowing_plan,
                self.gen._layer_model, progress_callback,
            )

            _rewrite_for_consistency_violations(
                self.config.pipeline, self.llm, chapter, outline,
                story_context, self.gen._layer_model, progress_callback,
            )

            _enforce_pacing(
                self.config.pipeline, self.llm, chapter, outline,
                self.gen._layer_model, progress_callback,
            )

            # Post-write contract validation with retry (#2 improvement)
            if contract is not None and getattr(self.config.pipeline, "enable_contract_validation", False):
                try:
                    from pipeline.layer1_story.chapter_contract_builder import validate_contract_compliance
                    compliance = validate_contract_compliance(
                        self.llm, chapter.content, contract, model=self.gen._layer_model,
                    )
                    _contract_failures = compliance.get("failures", [])
                    score = compliance.get("compliance_score", 0.0)

                    # Retry logic: if score below threshold, rewrite chapter
                    retry_count = 0
                    while score < self.retry_threshold and retry_count < self.retry_max:
                        retry_count += 1
                        if progress_callback:
                            progress_callback(
                                f"⚠️ Ch{outline.chapter_number} compliance {score:.0%} < {self.retry_threshold:.0%}, retry {retry_count}/{self.retry_max}..."
                            )
                        logger.info(
                            "Ch%d retry %d: compliance %.0f%% < %.0f%%, failures: %s",
                            outline.chapter_number, retry_count, score * 100,
                            self.retry_threshold * 100, _contract_failures,
                        )

                        # Rebuild contract with failure feedback
                        try:
                            from pipeline.layer1_story.chapter_contract_builder import build_contract, format_contract_for_prompt
                            contract = build_contract(
                                outline.chapter_number, outline,
                                threads=list(story_context.open_threads),
                                macro_arcs=macro_arcs,
                                conflicts=conflict_web,
                                foreshadowing_plan=foreshadowing_plan,
                                characters=characters,
                                previous_failures=_contract_failures,
                            )
                            contract_text = format_contract_for_prompt(contract)
                        except Exception as e:
                            logger.warning("Contract rebuild failed for ch%d retry: %s", outline.chapter_number, e)

                        # Rewrite chapter with updated contract
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
                                enhancement_context=enhancement_context,
                                current_arc_context=arc_context,
                                chapter_contract=contract_text,
                                scenes=chapter_scenes,
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
                                enhancement_context=enhancement_context,
                                current_arc_context=arc_context,
                                chapter_contract=contract_text,
                                scenes=chapter_scenes,
                            )

                        # Update in chapters list
                        chapters[-1] = chapter
                        all_chapter_texts[-1] = chapter.content

                        # Re-validate
                        compliance = validate_contract_compliance(
                            self.llm, chapter.content, contract, model=self.gen._layer_model,
                        )
                        _contract_failures = compliance.get("failures", [])
                        score = compliance.get("compliance_score", 0.0)

                    if score < 0.7:
                        logger.warning(
                            "Ch%d final compliance %.0f%% — failures: %s",
                            outline.chapter_number, score * 100, _contract_failures,
                        )
                    elif progress_callback:
                        progress_callback(
                            f"Chương {outline.chapter_number} hợp đồng: {score:.0%}"
                            + (f" (sau {retry_count} retry)" if retry_count > 0 else "")
                        )
                except Exception as e:
                    logger.warning("Contract validation failed for ch%d (non-fatal): %s", outline.chapter_number, e)
                    _contract_failures = []

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
                            batch, frozen, draft, story_context, all_chapter_texts,
                            title, genre, style, characters, world, word_count,
                            context_window, executor, self_reviewer, progress_callback,
                            macro_arcs, conflict_web, foreshadowing_plan, premise, voice_profiles,
                        )
                    )
                    return future.result()
            else:
                return asyncio.run(
                    self._run_batch_async(
                        batch, frozen, draft, story_context, all_chapter_texts,
                        title, genre, style, characters, world, word_count,
                        context_window, executor, self_reviewer, progress_callback,
                        macro_arcs, conflict_web, foreshadowing_plan, premise, voice_profiles,
                    )
                )
        else:
            return self._run_batch_threaded(
                batch, frozen, draft, story_context, all_chapter_texts,
                title, genre, style, characters, world, word_count,
                context_window, executor, self_reviewer, progress_callback,
                macro_arcs, conflict_web, foreshadowing_plan, premise, voice_profiles,
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
    ) -> list[Chapter]:
        """Async batch execution using asyncio.gather() (#1 improvement)."""
        sibling_summaries = self._build_sibling_context(batch)
        frozen_threads = list(story_context.open_threads)

        from pipeline.layer1_story.enhancement_context_builder import build_shared_enhancement_context
        shared_enhancement = build_shared_enhancement_context(
            self.config, genre, premise=premise, voice_profiles=voice_profiles,
        )

        # Causal accumulator for cross-chapter sync (#3 improvement)
        causal_acc = CausalAccumulator() if self.causal_sync else None

        async def _write_one_async(outline: ChapterOutline) -> tuple[Chapter, dict | None]:
            """Write single chapter in thread pool, return chapter + contract for retry."""
            return await asyncio.to_thread(
                self._write_chapter_parallel,
                outline, frozen, draft, story_context, frozen_threads,
                sibling_summaries, shared_enhancement, title, genre, style,
                characters, world, word_count, macro_arcs, conflict_web,
                foreshadowing_plan, progress_callback, causal_acc,
            )

        # Execute all chapters concurrently
        if progress_callback:
            progress_callback(f"[ASYNC] Đang viết {len(batch)} chương song song...")

        results = await asyncio.gather(
            *[_write_one_async(o) for o in batch],
            return_exceptions=True,
        )

        # Process results, handle errors
        chapters = []
        contracts = {}
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("Async write failed for chapter %d: %s", batch[i].chapter_number, result)
                raise result
            chapter, contract = result
            chapters.append(chapter)
            if contract:
                contracts[chapter.chapter_number] = contract

        # Sprint 2 Task 1: serial-index post-gather to avoid ChromaDB write contention
        for ch in chapters:
            outline_for_ch = next((o for o in batch if o.chapter_number == ch.chapter_number), None)
            if outline_for_ch is None:
                continue
            _index_chapter_into_rag(
                self.config, ch, outline_for_ch, characters,
                list(frozen_threads) if frozen_threads else None,
            )

        # Contract validation with retry (#2 improvement)
        if contracts and getattr(self.config.pipeline, "enable_contract_validation", False):
            chapters = await self._validate_and_retry_async(
                chapters, contracts, batch, frozen, draft, story_context,
                frozen_threads, sibling_summaries, shared_enhancement,
                title, genre, style, characters, world, word_count,
                macro_arcs, conflict_web, foreshadowing_plan, progress_callback,
            )

        chapters_ordered = sorted(chapters, key=lambda c: c.chapter_number)

        # Causal sync: merge accumulated events into story_context (#3 improvement)
        if causal_acc and self.causal_sync:
            self._sync_causal_events(causal_acc, story_context, progress_callback)

        if progress_callback:
            progress_callback(
                f"[BATCH] {len(chapters_ordered)} chương viết xong, đang trích xuất context..."
            )

        # Post-processing (sequential for consistency)
        for outline, chapter in zip(
            sorted(batch, key=lambda o: o.chapter_number), chapters_ordered
        ):
            all_chapter_texts.append(chapter.content)
            process_chapter_post_write(
                chapter, outline, story_context, characters, context_window,
                executor, self.llm, draft, self.gen.bible_manager,
                progress_callback, genre, word_count,
                self.config.pipeline.enable_self_review, self_reviewer,
                open_threads=frozen_threads,
                foreshadowing_plan=foreshadowing_plan,
                world_rules=getattr(draft.world, 'rules', None) or [],
                voice_profiles=getattr(draft, 'voice_profiles', None) or [],
                pipeline_config=self.config.pipeline,
            )
            _verify_and_rewrite_missing_payoffs(
                self.config.pipeline, self.llm, chapter, outline,
                story_context, foreshadowing_plan,
                self.gen._layer_model, progress_callback,
            )

            _rewrite_for_consistency_violations(
                self.config.pipeline, self.llm, chapter, outline,
                story_context, self.gen._layer_model, progress_callback,
            )

            _enforce_pacing(
                self.config.pipeline, self.llm, chapter, outline,
                self.gen._layer_model, progress_callback,
            )

        return chapters_ordered

    async def _validate_and_retry_async(
        self,
        chapters: list[Chapter],
        contracts: dict,
        batch: list[ChapterOutline],
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
    ) -> list[Chapter]:
        """Validate contracts and retry failed chapters (#2 improvement)."""
        from pipeline.layer1_story.chapter_contract_builder import validate_contract_compliance

        outline_map = {o.chapter_number: o for o in batch}
        chapter_map = {c.chapter_number: c for c in chapters}

        for ch_num, contract in contracts.items():
            chapter = chapter_map[ch_num]
            outline = outline_map[ch_num]

            try:
                compliance = await asyncio.to_thread(
                    validate_contract_compliance,
                    self.llm, chapter.content, contract, model=self.gen._layer_model,
                )
                score = compliance.get("compliance_score", 0.0)
                failures = compliance.get("failures", [])

                retry_count = 0
                while score < self.retry_threshold and retry_count < self.retry_max:
                    retry_count += 1
                    if progress_callback:
                        progress_callback(
                            f"⚠️ Ch{ch_num} compliance {score:.0%} < {self.retry_threshold:.0%}, "
                            f"async retry {retry_count}/{self.retry_max}..."
                        )

                    # Rebuild contract with failures
                    from pipeline.layer1_story.chapter_contract_builder import build_contract
                    new_contract = build_contract(
                        ch_num, outline,
                        threads=frozen_threads,
                        macro_arcs=macro_arcs,
                        conflicts=conflict_web,
                        foreshadowing_plan=foreshadowing_plan,
                        characters=characters,
                        previous_failures=failures,
                    )

                    # Rewrite chapter
                    new_chapter, _ = await asyncio.to_thread(
                        self._write_chapter_parallel,
                        outline, frozen, draft, story_context, frozen_threads,
                        sibling_summaries, shared_enhancement, title, genre, style,
                        characters, world, word_count, macro_arcs, conflict_web,
                        foreshadowing_plan, progress_callback, None,
                        override_contract=new_contract,
                    )

                    chapter_map[ch_num] = new_chapter

                    # Re-validate
                    compliance = await asyncio.to_thread(
                        validate_contract_compliance,
                        self.llm, new_chapter.content, new_contract, model=self.gen._layer_model,
                    )
                    score = compliance.get("compliance_score", 0.0)
                    failures = compliance.get("failures", [])

                if progress_callback:
                    status = f"Ch{ch_num} compliance: {score:.0%}"
                    if retry_count > 0:
                        status += f" (sau {retry_count} retry)"
                    progress_callback(status)

            except Exception as e:
                logger.warning("Contract validation failed for ch%d: %s", ch_num, e)

        return list(chapter_map.values())

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
        override_contract=None,
    ) -> tuple[Chapter, dict | None]:
        """Write a single chapter for parallel execution. Returns (chapter, contract)."""
        try:
            from services.trace_context import set_chapter, set_module
            set_chapter(outline.chapter_number)
            set_module("chapter_writer")
        except Exception:
            pass
        bible_ctx = ""
        if draft.story_bible:
            bible_ctx = self.gen.bible_manager.get_context_for_chapter(
                draft.story_bible,
                outline.chapter_number,
                recent_summaries=frozen.recent_summaries,
                character_states=frozen.character_states,
            )
        if sibling_summaries:
            bible_ctx = f"{bible_ctx}\n\n[Sibling outlines in this batch]\n{sibling_summaries}" if bible_ctx else f"[Sibling outlines in this batch]\n{sibling_summaries}"

        # Tiered context
        if getattr(self.config.pipeline, "enable_tiered_context", False):
            try:
                from pipeline.layer1_story.tiered_context_builder import build_tiered_context
                tiered = build_tiered_context(
                    chapter_num=outline.chapter_number,
                    chapters=list(draft.chapters),
                    outline=outline,
                    open_threads=frozen_threads,
                    story_bible=draft.story_bible,
                    all_chapter_texts=list(frozen.chapter_texts),
                    max_tokens=getattr(self.config.pipeline, "tiered_context_max_tokens", 3000),
                    max_promotions=getattr(self.config.pipeline, "tiered_max_promotions", 5),
                )
                if tiered:
                    bible_ctx = tiered
            except Exception as e:
                logger.warning("Tiered context failed for ch%d: %s", outline.chapter_number, e)

        frozen_ctx = StoryContext(total_chapters=story_context.total_chapters)
        frozen_ctx.current_chapter = outline.chapter_number
        frozen_ctx.recent_summaries = list(frozen.recent_summaries)
        frozen_ctx.character_states = list(frozen.character_states)
        frozen_ctx.plot_events = list(frozen.plot_events)

        # Resolve narrative context
        active_conflicts, seeds, payoffs, pacing, current_arc = [], [], [], "", None
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
            logger.warning("Narrative context failed for ch%d: %s", outline.chapter_number, e)

        arc_context = ""
        if current_arc:
            arc_context = (
                f"Arc {current_arc.arc_number}: {current_arc.name}\n"
                f"Xung đột trung tâm: {current_arc.central_conflict}\n"
                f"Nhân vật trọng tâm: {', '.join(current_arc.character_focus) if current_arc.character_focus else 'tất cả'}\n"
                f"Kết thúc arc: {current_arc.resolution}\n"
                f"Cung bậc cảm xúc: {current_arc.emotional_trajectory}"
            )

        per_chapter_enhancement = shared_enhancement
        if self.config.pipeline.enable_scene_decomposition:
            try:
                from pipeline.layer1_story.scene_decomposer import (
                    decompose_chapter_scenes, format_scenes_for_prompt, should_decompose,
                )
                if should_decompose(outline.chapter_number, pacing):
                    scenes = decompose_chapter_scenes(
                        self.llm, outline, characters, world, genre, model=self.gen._layer_model,
                    )
                    st = format_scenes_for_prompt(scenes)
                    if st:
                        per_chapter_enhancement = f"{shared_enhancement}\n\n{st}".strip()
            except Exception:
                pass

        # Scene beats
        from pipeline.layer1_story.scene_beat_generator import generate_scene_beats
        scene_beats = generate_scene_beats(
            self.llm, outline, characters, world, genre,
            model_tier=self.gen._layer_model or "cheap",
        )
        if scene_beats:
            per_chapter_enhancement += scene_beats

        # Contract
        p_contract = override_contract
        p_contract_text = ""
        if p_contract is None and getattr(self.config.pipeline, "enable_chapter_contracts", False):
            try:
                from pipeline.layer1_story.chapter_contract_builder import build_contract, format_contract_for_prompt
                p_contract = build_contract(
                    outline.chapter_number, outline,
                    threads=frozen_threads,
                    macro_arcs=macro_arcs,
                    conflicts=conflict_web,
                    foreshadowing_plan=foreshadowing_plan,
                    characters=characters,
                )
                p_contract_text = format_contract_for_prompt(p_contract)
            except Exception as e:
                logger.warning("Contract build failed for ch%d: %s", outline.chapter_number, e)
        elif p_contract:
            from pipeline.layer1_story.chapter_contract_builder import format_contract_for_prompt
            p_contract_text = format_contract_for_prompt(p_contract)

        if progress_callback:
            progress_callback(f"Đang viết chương {outline.chapter_number}: {outline.title}...")

        ch_result = self.gen._write_chapter_with_long_context(
            title, genre, style, characters, world, outline,
            word_count, frozen_ctx, list(frozen.chapter_texts), bible_ctx,
            open_threads=frozen_threads,
            active_conflicts=active_conflicts,
            foreshadowing_to_plant=seeds,
            foreshadowing_to_payoff=payoffs,
            pacing_type=pacing,
            enhancement_context=per_chapter_enhancement,
            current_arc_context=arc_context,
            chapter_contract=p_contract_text,
        )

        if p_contract is not None:
            try:
                ch_result.contract = p_contract
                object.__setattr__(ch_result, "negotiated_contract", p_contract.to_negotiated())
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
            logger.debug("Causal extraction failed for ch%d: %s", outline.chapter_number, e)

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
            progress_callback(f"[CAUSAL] Synced {len(events)} causal events from parallel batch")

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
    ) -> list[Chapter]:
        """Thread-based batch execution (fallback when asyncio disabled)."""
        sibling_summaries = self._build_sibling_context(batch)
        frozen_threads = list(story_context.open_threads)

        from pipeline.layer1_story.enhancement_context_builder import build_shared_enhancement_context
        shared_enhancement = build_shared_enhancement_context(
            self.config, genre, premise=premise, voice_profiles=voice_profiles,
        )

        causal_acc = CausalAccumulator() if self.causal_sync else None

        max_workers = min(len(batch), 5)
        with ThreadPoolExecutor(max_workers=max_workers) as write_executor:
            futures = {
                write_executor.submit(
                    self._write_chapter_parallel,
                    o, frozen, draft, story_context, frozen_threads,
                    sibling_summaries, shared_enhancement, title, genre, style,
                    characters, world, word_count, macro_arcs, conflict_web,
                    foreshadowing_plan, progress_callback, causal_acc,
                ): o for o in batch
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
                    logger.error("Threaded write failed for chapter %d: %s", outline.chapter_number, e)
                    raise

        # Contract validation with retry (#2 improvement)
        if contracts and getattr(self.config.pipeline, "enable_contract_validation", False):
            from pipeline.layer1_story.chapter_contract_builder import validate_contract_compliance
            outline_map = {o.chapter_number: o for o in batch}
            chapter_map = {c.chapter_number: c for c in chapters}

            for ch_num, contract in contracts.items():
                chapter = chapter_map[ch_num]
                outline = outline_map[ch_num]
                try:
                    compliance = validate_contract_compliance(
                        self.llm, chapter.content, contract, model=self.gen._layer_model,
                    )
                    score = compliance.get("compliance_score", 0.0)
                    failures = compliance.get("failures", [])

                    retry_count = 0
                    while score < self.retry_threshold and retry_count < self.retry_max:
                        retry_count += 1
                        if progress_callback:
                            progress_callback(
                                f"⚠️ Ch{ch_num} compliance {score:.0%}, retry {retry_count}/{self.retry_max}..."
                            )

                        from pipeline.layer1_story.chapter_contract_builder import build_contract
                        new_contract = build_contract(
                            ch_num, outline,
                            threads=frozen_threads,
                            macro_arcs=macro_arcs,
                            conflicts=conflict_web,
                            foreshadowing_plan=foreshadowing_plan,
                            characters=characters,
                            previous_failures=failures,
                        )

                        new_chapter, _ = self._write_chapter_parallel(
                            outline, frozen, draft, story_context, frozen_threads,
                            sibling_summaries, shared_enhancement, title, genre, style,
                            characters, world, word_count, macro_arcs, conflict_web,
                            foreshadowing_plan, progress_callback, None,
                            override_contract=new_contract,
                        )
                        chapter_map[ch_num] = new_chapter

                        compliance = validate_contract_compliance(
                            self.llm, new_chapter.content, new_contract, model=self.gen._layer_model,
                        )
                        score = compliance.get("compliance_score", 0.0)
                        failures = compliance.get("failures", [])

                    if progress_callback:
                        status = f"Ch{ch_num} compliance: {score:.0%}"
                        if retry_count > 0:
                            status += f" (sau {retry_count} retry)"
                        progress_callback(status)
                except Exception as e:
                    logger.warning("Contract validation failed for ch%d: %s", ch_num, e)

            chapters = list(chapter_map.values())

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
            process_chapter_post_write(
                chapter, outline, story_context, characters, context_window,
                executor, self.llm, draft, self.gen.bible_manager,
                progress_callback, genre, word_count,
                self.config.pipeline.enable_self_review, self_reviewer,
                open_threads=frozen_threads,
                foreshadowing_plan=foreshadowing_plan,
                world_rules=getattr(draft.world, 'rules', None) or [],
                voice_profiles=getattr(draft, 'voice_profiles', None) or [],
                pipeline_config=self.config.pipeline,
            )
            _verify_and_rewrite_missing_payoffs(
                self.config.pipeline, self.llm, chapter, outline,
                story_context, foreshadowing_plan,
                self.gen._layer_model, progress_callback,
            )

            _rewrite_for_consistency_violations(
                self.config.pipeline, self.llm, chapter, outline,
                story_context, self.gen._layer_model, progress_callback,
            )

            _enforce_pacing(
                self.config.pipeline, self.llm, chapter, outline,
                self.gen._layer_model, progress_callback,
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
