"""Layer execution methods for the 2-layer pipeline.

This module contains the concrete layer-running logic extracted from
PipelineOrchestrator to keep the main class focused on orchestration
rather than implementation details.
"""

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from models.schemas import EnhancedStory, PipelineOutput, StoryDraft
from plugins import plugin_manager
from pipeline.pipeline_utils import verify_draft_integrity, DraftIntegrityError
from services.trace_context import PipelineTrace, set_trace, clear_trace, set_module, set_chapter

if TYPE_CHECKING:
    from pipeline.orchestrator import PipelineOrchestrator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# P6: DB persistence helpers
# ---------------------------------------------------------------------------

def _persist_handoff_to_db(
    story_id: str,
    envelope_dict: dict,
    health_dict: dict,
    signals_version: str,
) -> None:
    """Write handoff fields to the most recent pipeline_run for story_id.

    Uses ORM (not raw SQL) so SQLAlchemy's UUID type adapter handles SQLite's
    dash-stripping correctly. Non-fatal if columns don't exist yet (pre-migration
    DB) — callers wrap in try/except.
    """
    import os
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from models.db_models import PipelineRun

    db_url = os.environ.get("DATABASE_URL", "sqlite:///data/storyforge.db")
    connect_args = {"check_same_thread": False} if "sqlite" in db_url else {}
    engine = create_engine(db_url, connect_args=connect_args)
    try:
        with Session(engine) as session:
            run = (
                session.query(PipelineRun)
                .filter(PipelineRun.story_id == story_id)
                .order_by(PipelineRun.created_at.desc())
                .first()
            )
            if run is None:
                logger.warning(
                    "Handoff DB persist: no pipeline_run found for story_id=%s", story_id
                )
                return
            run.handoff_envelope = envelope_dict
            run.handoff_health = health_dict
            run.handoff_signals_version = signals_version
            session.commit()
            logger.info(
                "Handoff persisted to pipeline_run id=%s story_id=%s", run.id, story_id
            )
    finally:
        engine.dispose()


def _persist_chapter_contract_to_db(
    story_id: str,
    chapter_number: int,
    contract_dict: dict,
    warnings: list,
) -> None:
    """Write negotiated_contract + warnings to chapters row.

    Uses ORM (not raw SQL) so SQLAlchemy's UUID type adapter handles SQLite's
    dash-stripping correctly. Non-fatal if columns don't exist (pre-migration).
    """
    import os
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from models.db_models import Chapter

    db_url = os.environ.get("DATABASE_URL", "sqlite:///data/storyforge.db")
    connect_args = {"check_same_thread": False} if "sqlite" in db_url else {}
    engine = create_engine(db_url, connect_args=connect_args)
    try:
        with Session(engine) as session:
            chapter = (
                session.query(Chapter)
                .filter(
                    Chapter.story_id == story_id,
                    Chapter.chapter_number == chapter_number,
                )
                .first()
            )
            if chapter is None:
                logger.warning(
                    "Chapter contract persist: no chapter found story_id=%s chapter_number=%d",
                    story_id, chapter_number,
                )
                return
            chapter.negotiated_contract = contract_dict
            chapter.contract_reconciliation_warnings = warnings
            session.commit()
            logger.info(
                "Chapter contract persisted story_id=%s chapter_number=%d",
                story_id, chapter_number,
            )
    finally:
        engine.dispose()


def persist_chapter_semantic_findings(
    story_id: str,
    chapter_number: int,
    findings_dict: dict,
) -> None:
    """Write semantic_findings JSON to chapters row (Sprint 2 P3).

    Uses ORM — not raw SQL — so SQLAlchemy's type adapters handle SQLite correctly.
    Non-fatal on missing column (pre-migration DB).
    """
    import os
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from models.db_models import Chapter

    db_url = os.environ.get("DATABASE_URL", "sqlite:///data/storyforge.db")
    connect_args = {"check_same_thread": False} if "sqlite" in db_url else {}
    engine = create_engine(db_url, connect_args=connect_args)
    try:
        with Session(engine) as session:
            chapter = (
                session.query(Chapter)
                .filter(
                    Chapter.story_id == story_id,
                    Chapter.chapter_number == chapter_number,
                )
                .first()
            )
            if chapter is None:
                logger.warning(
                    "Semantic findings persist: no chapter found story_id=%s chapter_number=%d",
                    story_id, chapter_number,
                )
                return
            chapter.semantic_findings = findings_dict
            session.commit()
            logger.debug(
                "Semantic findings persisted story_id=%s chapter_number=%d",
                story_id, chapter_number,
            )
    except Exception as exc:
        logger.warning(
            "Semantic findings persist failed (non-fatal) story_id=%s ch=%d: %s",
            story_id, chapter_number, exc,
        )
    finally:
        engine.dispose()


def persist_outline_metrics(
    story_id: str,
    metrics_dict: dict,
) -> None:
    """Write outline_metrics JSON to the most recent pipeline_run for story_id.

    Sprint 2 P5. Mirrors _persist_handoff_to_db pattern.  Non-fatal.
    """
    import os
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from models.db_models import PipelineRun

    db_url = os.environ.get("DATABASE_URL", "sqlite:///data/storyforge.db")
    connect_args = {"check_same_thread": False} if "sqlite" in db_url else {}
    engine = create_engine(db_url, connect_args=connect_args)
    try:
        with Session(engine) as session:
            run = (
                session.query(PipelineRun)
                .filter(PipelineRun.story_id == story_id)
                .order_by(PipelineRun.created_at.desc())
                .first()
            )
            if run is None:
                logger.warning(
                    "Outline metrics persist: no pipeline_run found for story_id=%s", story_id
                )
                return
            run.outline_metrics = metrics_dict
            session.commit()
            logger.info(
                "Outline metrics persisted to pipeline_run id=%s story_id=%s overall=%.3f",
                run.id, story_id, metrics_dict.get("overall_score", 0),
            )
    except Exception as exc:
        logger.warning(
            "Outline metrics persist failed (non-fatal) story_id=%s: %s",
            story_id, exc,
        )
    finally:
        engine.dispose()


async def _run_structural_rewrites(
    self: "PipelineOrchestrator",
    issues_by_chapter: dict,
    draft,
    genre: str,
    style: str,
    word_count: int,
    outline_map: dict,
    log_fn,
) -> tuple[list, list[tuple[int, BaseException]]]:
    """Run structural rewrites in bounded-concurrency batches.

    Concurrency capped to config.chapter_batch_size via asyncio.Semaphore.
    Each chapter's failure is isolated — siblings continue. Returns
    (rewritten_chapters, failed_list) where failed_list contains
    (chapter_number, exception) tuples for each rewrite that raised.
    """
    sem = asyncio.Semaphore(max(1, getattr(self.config.pipeline, "chapter_batch_size", 5)))

    async def _one(ch_num, issues):
        _fix_hints = "\n".join(f"- {i.fix_hint}" for i in issues)
        _issue_summary = "; ".join(i.description for i in issues)
        log_fn(f"[STRUCTURAL] Viết lại chương {ch_num}: {_issue_summary}")

        _outline = outline_map.get(ch_num)
        _enhancement_ctx = (
            f"[YÊU CẦU SỬA LỖI CẤU TRÚC]\n{_fix_hints}"
            if _fix_hints else ""
        )
        # Prepend drama directive if this chapter has a reconciled contract.
        _ch_contract = next(
            (getattr(c, "negotiated_contract", None)
             for c in draft.chapters if c.chapter_number == ch_num),
            None,
        )
        if _ch_contract is not None and getattr(_ch_contract, "drama_ceiling", 0.0) > 0:
            _subtext = ", ".join(_ch_contract.required_subtext) if _ch_contract.required_subtext else "không"
            _forbidden = ", ".join(_ch_contract.forbidden_patterns) if _ch_contract.forbidden_patterns else "không"
            _drama_directive = (
                "## RÀNG BUỘC KỊCH TÍNH"
                f"\n- Mục tiêu kịch tính: {_ch_contract.drama_target:.2f}"
                f"\n- Dung sai: ±{_ch_contract.drama_tolerance:.2f}"
                f"\n- Trần (KHÔNG vượt quá): {_ch_contract.drama_ceiling:.2f}"
                f"\n- Yêu cầu phụ văn (subtext): {_subtext}"
                f"\n- Cấm: {_forbidden}"
            )
            _enhancement_ctx = f"{_drama_directive}\n\n{_enhancement_ctx}" if _enhancement_ctx else _drama_directive

        async with sem:
            try:
                rewritten = await asyncio.to_thread(
                    self.story_gen.write_chapter,
                    title=draft.title,
                    genre=genre,
                    style=style,
                    characters=draft.characters,
                    world=draft.world,
                    outline=_outline,
                    word_count=word_count,
                    enhancement_context=_enhancement_ctx,
                )
                return ("ok", ch_num, rewritten)
            except Exception as exc:
                logger.warning(
                    "structural_rewrite_failed chapter=%s err=%s",
                    ch_num, exc,
                )
                return ("err", ch_num, exc)

    results = await asyncio.gather(
        *[_one(ch_num, issues) for ch_num, issues in sorted(issues_by_chapter.items())],
        return_exceptions=True,
    )

    rewritten = []
    failed: list[tuple[int, BaseException]] = []
    for r in results:
        if isinstance(r, BaseException):
            # asyncio.gather itself raised (should not happen with return_exceptions=True)
            logger.warning("structural_rewrite unexpected gather exception: %s", r)
        elif r[0] == "ok":
            rewritten.append((r[1], r[2]))  # (ch_num, Chapter)
        else:
            failed.append((r[1], r[2]))
    return rewritten, failed


async def run_full_pipeline(
    self: "PipelineOrchestrator",
    title: str,
    genre: str,
    idea: str,
    style: str = "Miêu tả chi tiết",
    num_chapters: int = 10,
    num_characters: int = 5,
    word_count: int = 2000,
    num_sim_rounds: int = 5,
    progress_callback=None,
    stream_callback=None,
    enable_agents: bool = True,
    enable_scoring: bool = True,
    enable_media: bool = False,
) -> PipelineOutput:
    """Chạy toàn bộ pipeline 2 lớp (story gen → drama sim).

    Async: all blocking LLM/IO calls are offloaded via asyncio.to_thread()
    so the event loop is never blocked. The RLock is kept for safety since
    to_thread workers run in a thread pool and can interleave.

    Delegates to _run_layer1, _run_layer2 in sequence.
    Each layer saves a checkpoint on success. Layer 2 failures are
    non-fatal — the pipeline continues with the original draft.
    """

    def _log(msg):
        with self._lock:
            self.output.logs.append(msg)
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    with self._lock:
        self.output = PipelineOutput(status="running", current_layer=1)
    self._sync_output()
    draft = None
    enhanced = None
    pipeline_start = time.time()

    # Trace instrumentation (Sprint 1 Task 2)
    trace = PipelineTrace(
        session_id=getattr(self, "session_id", "") or "",
        title=title or "",
        layer=1,
    )
    set_trace(trace)
    _log(f"[TRACE] Pipeline trace_id={trace.trace_id}")

    from services.progress_tracker import ProgressTracker
    tracker = ProgressTracker(callback=_log)

    # Verify LLM connectivity before spending compute
    from services.llm_client import LLMClient
    ok, msg = await asyncio.to_thread(LLMClient().check_connection)
    if not ok:
        self.output.status = "error"
        _log(f"Không kết nối được LLM: {msg}")
        return self.output

    # Optionally boot the multi-agent review panel
    AgentRegistry = None
    if enable_agents:
        try:
            from pipeline.agents import register_all_agents
            from pipeline.agents.agent_registry import AgentRegistry
            register_all_agents()
            _log("[AGENTS] Đã khởi tạo phòng ban đánh giá.")
        except Exception as e:
            logger.warning(f"Không thể khởi tạo agents: {e}")
            enable_agents = False

    # ── Layer 1: Story generation ────────────────────────────────────────────
    _log("══════ LAYER 1: TẠO TRUYỆN ══════")
    with self._lock:
        self.output.current_layer = 1
    set_module("layer1")
    layer_start = time.time()
    try:
        # Sprint 3 Task 2: per-chapter checkpoint callback (opt-in)
        _l1_chkpt_cb = None
        if getattr(self.config.pipeline, "enable_chapter_checkpoint", False):
            _bs = getattr(self.config.pipeline, "chapter_batch_size", 5)
            _every = max(1, getattr(self.config.pipeline, "chapter_checkpoint_every_n_batches", 1))
            _keep = getattr(self.config.pipeline, "chapter_checkpoint_keep_last", 5)
            self.checkpoint._chapter_keep_last = _keep

            def _l1_chkpt_cb(batch_done, total_batches):
                if batch_done % _every != 0 and batch_done != total_batches:
                    return
                last_ch = min(batch_done * _bs, num_chapters)
                try:
                    self.checkpoint.save_chapter(chapter_number=last_ch, layer=1, background=True)
                except Exception as e:
                    logger.warning(f"Chapter checkpoint save failed (non-fatal): {e}")

        draft = await asyncio.to_thread(
            self.story_gen.generate_full_story,
            title=title, genre=genre, idea=idea, style=style,
            num_chapters=num_chapters, num_characters=num_characters,
            word_count=word_count,
            progress_callback=lambda m: _log(f"[L1] {m}"),
            stream_callback=stream_callback,
            batch_checkpoint_callback=_l1_chkpt_cb,
        )
        with self._lock:
            self.output.story_draft = draft
            self.output.progress = 0.33
        _log(f"Layer 1 hoàn tất trong {time.time() - layer_start:.1f}s")

        # Surface context health (Sprint 1 Task 1)
        try:
            _l1_ctx = getattr(draft, "context", None)
            if _l1_ctx is not None:
                self.output.context_health_score = _l1_ctx.compute_health_score()
                self.output.extraction_failures = [e for e in _l1_ctx.extraction_health if not e.success]
                _log(
                    f"[HEALTH] Context health: {self.output.context_health_score:.0%} "
                    f"({len(self.output.extraction_failures)} failed extractions)"
                )
        except Exception as _h_err:
            logger.warning(f"Context health surface failed (non-fatal): {_h_err}")

        await asyncio.to_thread(self.checkpoint.save, 1)

        # Optional quality scoring
        l1_score = None
        if enable_scoring:
            tracker.scoring_started(1)
            try:
                from services.quality_scorer import QualityScorer
                scorer = QualityScorer()
                l1_score = await asyncio.to_thread(scorer.score_story, draft.chapters, layer=1)
                # Plugin hook: let plugins observe/modify quality scores
                try:
                    score_dict = {
                        "coherence": l1_score.avg_coherence,
                        "character_consistency": l1_score.avg_character,
                        "drama": l1_score.avg_drama,
                        "writing_quality": l1_score.avg_writing,
                        "overall": l1_score.overall,
                    }
                    updated = plugin_manager.apply_score(score_dict)
                    l1_score.avg_coherence = updated.get("coherence", l1_score.avg_coherence)
                    l1_score.avg_character = updated.get("character_consistency", l1_score.avg_character)
                    l1_score.avg_drama = updated.get("drama", l1_score.avg_drama)
                    l1_score.avg_writing = updated.get("writing_quality", l1_score.avg_writing)
                    l1_score.overall = updated.get("overall", l1_score.overall)
                except Exception as _e:
                    logger.warning(f"Plugin apply_score Layer 1 failed: {_e}")
                self.output.quality_scores.append(l1_score)
                tracker.scoring_done(1, l1_score.overall)
                _log(f"[METRICS] Layer 1: {l1_score.overall:.1f}/5 | "
                     f"Chương yếu nhất: {l1_score.weakest_chapter}")
            except Exception as e:
                logger.warning(f"Quality scoring Layer 1 failed: {e}")
                l1_score = None

        # Optional quality gate (may trigger a single retry)
        if enable_scoring and self.config.pipeline.enable_quality_gate:
            try:
                from services.quality_gate import QualityGate
                gate = QualityGate(
                    gate_threshold=self.config.pipeline.quality_gate_threshold,
                    chapter_threshold=self.config.pipeline.quality_gate_chapter_threshold,
                    max_retries=self.config.pipeline.quality_gate_max_retries,
                )
                tracker.gate_started(1)
                gate_result = gate.check(l1_score if self.output.quality_scores else None)
                _log(f"[GATE] {gate_result.message}")
                if gate_result.passed:
                    tracker.gate_passed(1, l1_score.overall if l1_score else 0.0)
                elif gate_result.should_retry:
                    tracker.gate_retry(1, l1_score.overall if l1_score else 0.0, attempt=1)
                    _log("[GATE] Đang thử tạo lại Layer 1...")
                    draft = await asyncio.to_thread(
                        self.story_gen.generate_full_story,
                        title=title, genre=genre, idea=idea, style=style,
                        num_chapters=num_chapters, num_characters=num_characters,
                        word_count=word_count,
                        progress_callback=lambda m: _log(f"[L1-RETRY] {m}"),
                        stream_callback=stream_callback,
                    )
                    self.output.story_draft = draft
                    # Re-score after retry
                    try:
                        from services.quality_scorer import QualityScorer
                        scorer = QualityScorer()
                        l1_score = await asyncio.to_thread(scorer.score_story, draft.chapters, layer=1)
                        self.output.quality_scores[-1] = l1_score
                    except Exception as e:
                        logger.warning(f"Quality scoring L1-retry failed: {e}")
                        l1_score = None
                    gate_result = gate.check(l1_score, retry_count=1)
                    _log(f"[GATE] Retry result: {gate_result.message}")
                    if gate_result.passed:
                        tracker.gate_passed(1, l1_score.overall if l1_score else 0.0)
                    else:
                        tracker.gate_failed(1, l1_score.overall if l1_score else 0.0)
                else:
                    tracker.gate_failed(1, l1_score.overall if l1_score else 0.0)
            except Exception as e:
                logger.warning(f"Quality gate Layer 1 failed: {e}")

        # Auto analytics: word count, reading time, dialogue ratio
        try:
            from services.story_analytics import StoryAnalytics
            analytics = await asyncio.to_thread(StoryAnalytics.analyze_story, draft)
            self.output.analytics = {"layer1": analytics}
            _log(f"[ANALYTICS] Layer 1: {analytics['total_words']} từ, "
                 f"{analytics['reading_time_minutes']} phút đọc, "
                 f"dialogue: {analytics['dialogue_ratio']:.0%}")
        except Exception as e:
            logger.warning(f"Analytics Layer 1 failed: {e}")

        # Build knowledge graph to track character/location relationships.
        # Sprint 3 Task 1: when enable_unified_kg is on, merge conflict_web + threads +
        # foreshadowing + macro_arcs into a single graph and persist full serialized form.
        try:
            from services.knowledge_graph import StoryKnowledgeGraph
            use_unified = bool(getattr(self.config.pipeline, "enable_unified_kg", False))
            builder = (StoryKnowledgeGraph().build_unified if use_unified
                       else StoryKnowledgeGraph().build_from_story_draft)
            kg = await asyncio.to_thread(builder, draft)
            self.output.knowledge_graph_summary = kg.to_summary()
            if use_unified:
                serialized = kg.to_dict()
                self.output.knowledge_graph = serialized
                draft.knowledge_graph = serialized
            _log(f"[KG] Knowledge graph: {kg.node_count()} nodes, {kg.edge_count()} edges"
                 f"{' (unified)' if use_unified else ''}")
        except Exception as e:
            logger.warning(f"Knowledge graph build failed: {e}")

        # Multi-agent review panel for Layer 1
        if enable_agents:
            _log("[AGENTS] Phòng ban đang đánh giá Layer 1...")
            try:
                reviews = await asyncio.to_thread(
                    AgentRegistry().run_review_cycle,
                    self.output, layer=1, max_iterations=3,
                    progress_callback=lambda m: _log(m),
                )
                self.output.reviews.extend(reviews)
            except Exception as e:
                logger.warning(f"Agent review Layer 1 lỗi: {e}")
    except Exception as e:
        self.output.status = "error"
        _log(f"Layer 1 thất bại: {str(e)}")
        logger.exception("Layer 1 error")
        return self.output

    if not draft or not draft.chapters:
        _log("[ERROR] Layer 1 produced no chapters. Cannot proceed.")
        self.output.status = "error"
        return self.output

    # Bug #2: Draft integrity validation gate before L2
    try:
        integrity = verify_draft_integrity(
            draft,
            require_chapters=True,
            require_outlines=True,
            require_characters=True,
            min_chapters=1,
        )
        if not integrity["valid"]:
            _log(f"[INTEGRITY] ⚠️ Draft có vấn đề: {'; '.join(integrity['errors'])}")
        for warn in integrity.get("warnings", []):
            _log(f"[INTEGRITY] {warn}")
        _log(f"[INTEGRITY] {integrity['chapter_count']} chapters, {integrity['character_count']} characters")
    except DraftIntegrityError as e:
        _log(f"[INTEGRITY] Draft integrity check failed: {e}")
        self.output.status = "error"
        return self.output

    # Sprint 1 P3/P6: L1 → L2 handoff validation gate + DB persistence.
    # P2 attached `draft.l1_handoff` as a dict; re-hydrate to typed model and enforce.
    handoff_envelope = None
    try:
        from models.handoff_schemas import L1Handoff
        from pipeline.handoff_gate import enforce_handoff, HandoffValidationError

        _raw_envelope = getattr(draft, "l1_handoff", None)
        if isinstance(_raw_envelope, dict) and _raw_envelope:
            handoff_envelope = L1Handoff.model_validate(_raw_envelope)
            try:
                handoff_envelope = enforce_handoff(handoff_envelope)
            except HandoffValidationError as exc:
                _log(f"[HANDOFF] Strict-mode block: {exc}")
                self.output.status = "error"
                self.output.handoff_health = {
                    sig: h.model_dump() for sig, h in handoff_envelope.signal_health.items()
                }
                return self.output

            # P6: structured log line at handoff
            _ok_signals = [s for s, h in handoff_envelope.signal_health.items() if h.status == "ok"]
            _missing = [s for s, h in handoff_envelope.signal_health.items() if h.status in ("empty", "extraction_failed")]
            logger.info(
                "handoff_built signals_ok=%d/%d missing=%s story_id=%s",
                len(_ok_signals),
                len(handoff_envelope.signal_health),
                _missing,
                handoff_envelope.story_id,
            )
            _log(
                f"[HANDOFF] story_id={handoff_envelope.story_id} "
                f"signals_ok={len(_ok_signals)}/{len(handoff_envelope.signal_health)} "
                f"missing={_missing}"
            )

            # Persist handoff fields to pipeline_runs row (P6)
            _handoff_health_dict = {
                sig: h.model_dump() for sig, h in handoff_envelope.signal_health.items()
            }
            self.output.handoff_health = _handoff_health_dict
            # Stash envelope dict on output so pipeline_output_builder can extract story_id
            self.output.handoff_envelope = handoff_envelope.model_dump()
            try:
                _persist_handoff_to_db(
                    story_id=handoff_envelope.story_id,
                    envelope_dict=handoff_envelope.model_dump(),
                    health_dict=_handoff_health_dict,
                    signals_version=handoff_envelope.signals_version,
                )
            except Exception as _pe:
                logger.warning("Handoff DB persist failed (non-fatal): %s", _pe)

            # Stash typed envelope on draft so P4 has a clean handle.
            draft._l1_handoff_envelope = handoff_envelope
        else:
            _log("[HANDOFF] No envelope on draft (P2 build skipped or failed); continuing.")
    except Exception as _h_err:  # pragma: no cover — defensive
        logger.warning(f"Handoff gate failed (non-fatal): {_h_err}")

    # ── Structural rewrite: L2 detects issues → L1 rewrites before enhancement ──
    _structural_rewrite_enabled = getattr(self.config.pipeline, "enable_structural_rewrite", True)
    if _structural_rewrite_enabled:
        try:
            _rewrite_threshold = float(getattr(self.config.pipeline, "structural_rewrite_threshold", 0.7))
            _max_rewrites = int(getattr(self.config.pipeline, "max_structural_rewrites", 1))

            # Collect arc waypoints from draft characters
            _sr_arc_wps: list = []
            for _c in (draft.characters or []):
                for _wp in (getattr(_c, "arc_waypoints", None) or []):
                    _wd = _wp.model_dump() if hasattr(_wp, "model_dump") else _wp
                    if isinstance(_wd, dict):
                        _wd.setdefault("character", _c.name)
                        _sr_arc_wps.append(_wd)

            issues_by_chapter = self.enhancer.detect_structural_issues(
                draft, arc_waypoints=_sr_arc_wps, threshold=_rewrite_threshold
            )

            if issues_by_chapter:
                _log(f"[STRUCTURAL] Phát hiện vấn đề cấu trúc trong {len(issues_by_chapter)} chương")
                _outline_map = {o.chapter_number: o for o in (draft.outlines or [])}

                # Apply max_rewrites cap: keep only the first N chapter entries.
                _capped_issues = dict(
                    list(sorted(issues_by_chapter.items()))[: _max_rewrites * len(draft.chapters)]
                )

                # Pipeline stats counters (P6 observability)
                _sr_attempted = len(_capped_issues)

                # ── P6: bounded-concurrency parallel rewrite (D4) ────────────
                _rewritten_pairs, _failed_pairs = await _run_structural_rewrites(
                    self,
                    issues_by_chapter=_capped_issues,
                    draft=draft,
                    genre=genre,
                    style=style,
                    word_count=word_count,
                    outline_map=_outline_map,
                    log_fn=_log,
                )

                _sr_succeeded = len(_rewritten_pairs)
                _sr_failed = len(_failed_pairs)

                # Merge stats into output.analytics["pipeline_stats"]
                _stats = self.output.analytics.setdefault("pipeline_stats", {})
                _stats["structural_rewrites_attempted"] = (
                    _stats.get("structural_rewrites_attempted", 0) + _sr_attempted
                )
                _stats["structural_rewrites_succeeded"] = (
                    _stats.get("structural_rewrites_succeeded", 0) + _sr_succeeded
                )
                _stats["structural_rewrites_failed"] = (
                    _stats.get("structural_rewrites_failed", 0) + _sr_failed
                )

                # Apply successful rewrites back into draft
                for _ch_num, _rewritten_ch in _rewritten_pairs:
                    for _idx, _ch in enumerate(draft.chapters):
                        if _ch.chapter_number == _ch_num:
                            draft.chapters[_idx] = _rewritten_ch
                            break
                    self.enhancer._rewritten_chapters.add(_ch_num)
                    _log(f"[STRUCTURAL] Chương {_ch_num} đã viết lại xong")

                # Surface failures (already logged per-chapter in helper)
                for _ch_num, _err in _failed_pairs:
                    logger.warning("Structural rewrite ch%s failed (non-fatal): %s", _ch_num, _err)

                if _sr_failed:
                    _log(
                        f"[STRUCTURAL] Hoàn tất: {_sr_succeeded}/{_sr_attempted} chương thành công "
                        f"({_sr_failed} thất bại)"
                    )
            else:
                _log("[STRUCTURAL] Không phát hiện vấn đề cấu trúc nghiêm trọng")
        except Exception as _sr_err:
            logger.warning(f"Structural rewrite phase failed (non-fatal): {_sr_err}")

    # ── Layer 2: Drama simulation & story enhancement ────────────────────────
    _log("══════ LAYER 2: MÔ PHỎNG TĂNG KỊCH TÍNH ══════")
    with self._lock:
        self.output.current_layer = 2
    set_module("layer2")
    set_chapter(None)
    # Route subsequent LLM calls into the L2 usage sidecar.
    trace.layer = 2
    layer_start = time.time()
    try:
        _log("[L2] Đang phân tích cấu trúc truyện...")

        # Extract theme for L2 enhancement (non-fatal)
        theme_profile = None
        try:
            from pipeline.layer2_enhance.thematic_tracker import ThematicTracker
            thematic = ThematicTracker()
            theme_profile = await asyncio.to_thread(thematic.extract_theme, draft)
            if theme_profile and theme_profile.central_theme:
                _log(f"[L2] Chủ đề: {theme_profile.central_theme}")
            else:
                _log("[L2] Không trích xuất được chủ đề trung tâm")
        except Exception as e:
            logger.warning(f"Theme extraction failed (non-fatal): {e}")

        # Plugin hook: allow plugins to observe/override genre drama rules
        try:
            from pipeline.layer2_enhance.drama_patterns import get_genre_rules
            base_rules = get_genre_rules(genre)
            plugin_manager.apply_genre_rules(genre, base_rules)
        except Exception as _e:
            logger.warning(f"Plugin apply_genre_rules failed: {_e}")

        _use_signals = bool(getattr(self.config.pipeline, "l2_use_l1_signals", True))
        _arc_wps = []
        _threads_in = None
        _pacing_dir = ""
        _conflict_web = None
        _foreshadowing_plan = None
        if _use_signals:
            for c in (draft.characters or []):
                wps = getattr(c, "arc_waypoints", None) or []
                for wp in wps:
                    wd = wp.model_dump() if hasattr(wp, "model_dump") else wp
                    if isinstance(wd, dict):
                        wd.setdefault("character", c.name)
                        _arc_wps.append(wd)
            _threads_in = list(getattr(draft, "open_threads", []) or []) + list(getattr(draft, "resolved_threads", []) or [])
            try:
                _ctx = getattr(draft, "context", None)
                _pacing_dir = str(getattr(_ctx, "pacing_adjustment", "") or "") if _ctx else ""
            except Exception:
                _pacing_dir = ""
            _conflict_web = list(getattr(draft, "conflict_web", None) or []) or None
            _foreshadowing_plan = list(getattr(draft, "foreshadowing_plan", None) or []) or None

        # Adaptive simulation rounds: calculate based on story complexity if enabled
        if getattr(self.config.pipeline, "adaptive_simulation_rounds", True):
            from pipeline.layer2_enhance.simulator import calculate_adaptive_rounds
            num_sim_rounds = calculate_adaptive_rounds(
                characters=draft.characters or [],
                threads=_threads_in,
                conflict_web=_conflict_web,
            )
            _log(f"[L2] Bắt đầu mô phỏng {num_sim_rounds} vòng (adaptive)...")
        else:
            _log(f"[L2] Bắt đầu mô phỏng {num_sim_rounds} vòng...")

        analysis = await asyncio.to_thread(
            self.analyzer.analyze, draft, _conflict_web
        )
        sim_result = await asyncio.to_thread(
            self.simulator.run_simulation,
            characters=draft.characters,
            relationships=analysis["relationships"],
            genre=genre,
            num_rounds=num_sim_rounds,
            progress_callback=lambda m: _log(f"[L2] {m}"),
            drama_intensity=self.config.pipeline.drama_intensity,
            pacing_directive=_pacing_dir,
            arc_waypoints=_arc_wps,
            threads=_threads_in,
            current_chapter=1,
            conflict_web=_conflict_web,
            foreshadowing_plan=_foreshadowing_plan,
        )
        self.output.simulation_result = sim_result

        # Expose live simulator state to enhancer via draft private attrs (Phase B causal audit)
        try:
            draft._knowledge_registry = getattr(self.simulator, "knowledge", None)
            draft._causal_graph = getattr(self.simulator, "causal_graph", None)
        except Exception:
            pass

        if hasattr(sim_result, 'actual_rounds') and sim_result.actual_rounds:
            _log(f"[L2] Adaptive: {sim_result.actual_rounds} rounds (requested {num_sim_rounds})")
        if hasattr(sim_result, 'knowledge_state') and sim_result.knowledge_state:
            total_facts = sum(len(v) for v in sim_result.knowledge_state.values())
            _log(f"[L2] Knowledge: {total_facts} sự kiện theo dõi, {len(sim_result.knowledge_state)} nhân vật")

        _log("[L2] Đang viết lại truyện với kịch tính cao hơn...")
        enhanced = await self.enhancer.enhance_with_feedback_async(
            draft=draft, sim_result=sim_result,
            word_count=word_count,
            progress_callback=lambda m: _log(f"[L2] {m}"),
            theme_profile=theme_profile,
        )
        with self._lock:
            self.output.enhanced_story = enhanced
            self.output.progress = 0.66
        _log(f"Layer 2 hoàn tất trong {time.time() - layer_start:.1f}s")
        await asyncio.to_thread(self.checkpoint.save, 2)

        # Optional quality scoring for Layer 2
        l2_score = None
        if enable_scoring:
            tracker.scoring_started(2)
            try:
                from services.quality_scorer import QualityScorer
                scorer = QualityScorer()
                l2_score = await asyncio.to_thread(scorer.score_story, enhanced.chapters, layer=2)
                # Plugin hook: let plugins observe/modify Layer 2 quality scores
                try:
                    score_dict = {
                        "coherence": l2_score.avg_coherence,
                        "character_consistency": l2_score.avg_character,
                        "drama": l2_score.avg_drama,
                        "writing_quality": l2_score.avg_writing,
                        "overall": l2_score.overall,
                    }
                    updated = plugin_manager.apply_score(score_dict)
                    l2_score.avg_coherence = updated.get("coherence", l2_score.avg_coherence)
                    l2_score.avg_character = updated.get("character_consistency", l2_score.avg_character)
                    l2_score.avg_drama = updated.get("drama", l2_score.avg_drama)
                    l2_score.avg_writing = updated.get("writing_quality", l2_score.avg_writing)
                    l2_score.overall = updated.get("overall", l2_score.overall)
                except Exception as _e:
                    logger.warning(f"Plugin apply_score Layer 2 failed: {_e}")
                self.output.quality_scores.append(l2_score)
                tracker.scoring_done(2, l2_score.overall)
                delta = ""
                if len(self.output.quality_scores) >= 2:
                    diff = l2_score.overall - self.output.quality_scores[0].overall
                    delta = f" | Delta: {diff:+.1f}"
                _log(f"[METRICS] Layer 2: {l2_score.overall:.1f}/5 | "
                     f"Chương yếu nhất: {l2_score.weakest_chapter}{delta}")
            except Exception as e:
                logger.warning(f"Quality scoring Layer 2 failed: {e}")
                l2_score = None

        # Optional quality gate for Layer 2
        if enable_scoring and self.config.pipeline.enable_quality_gate:
            try:
                from services.quality_gate import QualityGate
                gate = QualityGate(
                    gate_threshold=self.config.pipeline.quality_gate_threshold,
                    chapter_threshold=self.config.pipeline.quality_gate_chapter_threshold,
                    max_retries=self.config.pipeline.quality_gate_max_retries,
                )
                # Use last appended score (Layer 2)
                l2_check_score = self.output.quality_scores[-1] if self.output.quality_scores else None
                tracker.gate_started(2)
                gate_result = gate.check(l2_check_score)
                _log(f"[GATE] {gate_result.message}")
                if gate_result.passed:
                    tracker.gate_passed(2, l2_check_score.overall if l2_check_score else 0.0)
                elif gate_result.should_retry:
                    tracker.gate_retry(2, l2_check_score.overall if l2_check_score else 0.0, attempt=1)
                    _log("[GATE] Đang thử tạo lại Layer 2...")
                    enhanced = await self.enhancer.enhance_with_feedback_async(
                        draft=draft, sim_result=sim_result,
                        word_count=word_count,
                        progress_callback=lambda m: _log(f"[L2-RETRY] {m}"),
                    )
                    self.output.enhanced_story = enhanced
                    # Re-score after retry
                    try:
                        from services.quality_scorer import QualityScorer
                        scorer = QualityScorer()
                        l2_score = await asyncio.to_thread(scorer.score_story, enhanced.chapters, layer=2)
                        self.output.quality_scores[-1] = l2_score
                    except Exception as e:
                        logger.warning(f"Quality scoring L2-retry failed: {e}")
                        l2_score = None
                    gate_result = gate.check(l2_score, retry_count=1)
                    _log(f"[GATE] Retry result: {gate_result.message}")
                    if gate_result.passed:
                        tracker.gate_passed(2, l2_score.overall if l2_score else 0.0)
                    else:
                        tracker.gate_failed(2, l2_score.overall if l2_score else 0.0)
                else:
                    tracker.gate_failed(2, l2_check_score.overall if l2_check_score else 0.0)
            except Exception as e:
                logger.warning(f"Quality gate Layer 2 failed: {e}")

        # Auto analytics for enhanced story
        try:
            from services.story_analytics import StoryAnalytics
            analytics = await asyncio.to_thread(StoryAnalytics.analyze_story, enhanced)
            self.output.analytics["layer2"] = analytics
            _log(f"[ANALYTICS] Layer 2: {analytics['total_words']} từ, "
                 f"{analytics['reading_time_minutes']} phút đọc, "
                 f"dialogue: {analytics['dialogue_ratio']:.0%}")
        except Exception as e:
            logger.warning(f"Analytics Layer 2 failed: {e}")

        # L2 enhanced metrics (non-fatal)
        try:
            if sim_result:
                self.output.analytics.setdefault("layer2", {})
                self.output.analytics["layer2"]["actual_rounds"] = getattr(sim_result, "actual_rounds", 0)
                self.output.analytics["layer2"]["causal_chains"] = len(getattr(sim_result, "causal_chains", []))
            if theme_profile:
                self.output.analytics.setdefault("layer2", {})
                self.output.analytics["layer2"]["theme"] = theme_profile.central_theme
        except Exception as e:
            logger.warning(f"L2 analytics extension failed: {e}")

        # Sprint 1 Task 3: contract validation stats
        try:
            from pipeline.layer2_enhance.chapter_contract import (
                ContractValidation, aggregate_contract_stats,
            )
            _validations = []
            for _ch in (enhanced.chapters or []):
                _cv = getattr(_ch, "contract_validation", None)
                if isinstance(_cv, dict) and _cv:
                    try:
                        _validations.append(ContractValidation(**_cv))
                    except Exception:
                        continue
            if _validations:
                self.output.analytics.setdefault("layer2", {})
                self.output.analytics["layer2"]["contract_stats"] = aggregate_contract_stats(_validations)
                _log(
                    f"[CONTRACT] stats: {self.output.analytics['layer2']['contract_stats']}"
                )
        except Exception as e:
            logger.warning(f"Contract stats aggregation failed: {e}")

        # Sprint 1 P5: fill L2 portion onto NegotiatedChapterContract from
        # sim_result, then reconcile (single rubric — drama_target is now part
        # of the negotiated contract, no parallel DramaContract).
        try:
            from models.handoff_schemas import NegotiatedChapterContract
            from pipeline.handoff_gate import reconcile_contract
            from pipeline.layer2_enhance.chapter_contract import build_chapter_contracts

            _ch_nums = [int(getattr(_c, "chapter_number", 0) or 0) for _c in (enhanced.chapters or [])]
            _drama_by_ch: dict[int, NegotiatedChapterContract] = {}
            if sim_result is not None and _ch_nums:
                try:
                    _drama_by_ch = build_chapter_contracts(sim_result, _ch_nums)
                except Exception as _be:
                    logger.debug(f"build_chapter_contracts skipped: {_be}")

            for _ch in (enhanced.chapters or []):
                _nc = getattr(_ch, "negotiated_contract", None)
                _typed: NegotiatedChapterContract | None = None
                if isinstance(_nc, NegotiatedChapterContract):
                    _typed = _nc
                elif isinstance(_nc, dict) and _nc:
                    try:
                        _typed = NegotiatedChapterContract.model_validate(_nc)
                    except Exception:
                        _typed = None
                if _typed is None:
                    continue
                _drama = _drama_by_ch.get(int(_ch.chapter_number))
                if _drama is not None:
                    _typed = _typed.model_copy(update={
                        "drama_target": float(_drama.drama_target),
                        "drama_tolerance": float(_drama.drama_tolerance),
                        "escalation_events": list(_drama.escalation_events),
                        "required_subtext": list(_drama.required_subtext),
                        "causal_refs": list(_drama.causal_refs),
                        "forbidden_patterns": list(_drama.forbidden_patterns),
                    })
                _reconciled = reconcile_contract(_typed, sim_result=sim_result)
                try:
                    object.__setattr__(_ch, "negotiated_contract", _reconciled)
                except Exception:
                    pass
                # P6: persist reconciled contract to DB
                try:
                    _r_dict = _reconciled.model_dump()
                    _r_warns = list(_reconciled.reconciliation_warnings)
                    _story_id_for_ch = (
                        handoff_envelope.story_id if handoff_envelope else None
                    )
                    if _story_id_for_ch:
                        _persist_chapter_contract_to_db(
                            story_id=_story_id_for_ch,
                            chapter_number=int(_ch.chapter_number),
                            contract_dict=_r_dict,
                            warnings=_r_warns,
                        )
                except Exception as _cp_err:
                    logger.debug("Chapter contract DB persist skipped: %s", _cp_err)
        except Exception as _rc_err:
            logger.warning(f"Contract reconciliation failed (non-fatal): {_rc_err}")

        # Sprint 2 Task 2: voice validation stats
        try:
            from pipeline.layer2_enhance.chapter_contract import (
                VoiceValidation, aggregate_voice_stats,
            )
            _v_validations = []
            for _ch in (enhanced.chapters or []):
                _vv = getattr(_ch, "voice_validation", None)
                if isinstance(_vv, dict) and _vv:
                    try:
                        _v_validations.append(VoiceValidation(**_vv))
                    except Exception:
                        continue
            # Rough LLM-calls-saved estimate: N characters × N chapters (old per-char-per-chapter path)
            _chars = len(getattr(draft, "characters", []) or [])
            _chaps = len(getattr(draft, "chapters", []) or [])
            _saved = _chars * _chaps if getattr(draft, "voice_profiles", None) else 0
            if _v_validations or _saved:
                self.output.analytics.setdefault("layer2", {})
                self.output.analytics["layer2"]["voice_stats"] = aggregate_voice_stats(
                    _v_validations, llm_calls_saved=_saved,
                )
                _log(
                    f"[VOICE] stats: {self.output.analytics['layer2']['voice_stats']}"
                )
        except Exception as e:
            logger.warning(f"Voice stats aggregation failed: {e}")

        # Multi-agent review panel for Layer 2
        if enable_agents:
            _log("[AGENTS] Phòng ban đang đánh giá Layer 2...")
            try:
                reviews = await asyncio.to_thread(
                    AgentRegistry().run_review_cycle,
                    self.output, layer=2, max_iterations=3,
                    progress_callback=lambda m: _log(m),
                )
                self.output.reviews.extend(reviews)
            except Exception as e:
                logger.warning(f"Agent review Layer 2 lỗi: {e}")

        # Smart chapter revision: auto-fix weak chapters using agent reviews
        if enable_scoring and self.config.pipeline.enable_smart_revision:
            _log("[REVISION] Kiểm tra chương yếu...")
            try:
                from services.smart_revision import SmartRevisionService
                revisor = SmartRevisionService(
                    threshold=self.config.pipeline.smart_revision_threshold
                )

                def _revision_progress(m: str):
                    _log(f"[REVISION] {m}")

                revision_result = await asyncio.to_thread(
                    revisor.revise_weak_chapters,
                    enhanced_story=enhanced,
                    quality_scores=self.output.quality_scores,
                    reviews=self.output.reviews,
                    genre=genre,
                    progress_callback=_revision_progress,
                )
                total_weak = revision_result.get("total_weak", 0)
                revised_count = revision_result.get("revised_count", 0)
                if total_weak > 0:
                    tracker.revision_started(total_weak)
                if revised_count > 0:
                    tracker.revision_done(revised_count, total_weak)
                    _log(f"[REVISION] Đã sửa {revised_count}/{total_weak} chương yếu")
            except Exception as e:
                logger.warning(f"Smart revision failed: {e}")
    except Exception as e:
        # Layer 2 failure is non-fatal: fall back to the original draft
        logger.warning(f"Layer 2 thất bại, dùng bản thảo gốc: {e}")
        _log(f"Layer 2 lỗi ({str(e)}), tiếp tục với bản thảo gốc.")
        enhanced = EnhancedStory(
            title=draft.title,
            genre=draft.genre,
            chapters=list(draft.chapters),
            enhancement_notes=[
                "Layer 2 skipped due to error",
                f"Error: {str(e)[:200]}",
                "Using original draft chapters — drama score will be 0",
            ],
            drama_score=0.0,
        )
        with self._lock:
            self.output.enhanced_story = enhanced
            self.output.progress = 0.66
            self.output.status = "partial"

    if not enhanced or not enhanced.chapters:
        _log("[ERROR] No chapters available after Layer 2. Pipeline stopping.")
        self.output.status = "error"
        return self.output

    with self._lock:
        self.output.progress = 1.0
        if self.output.status != "partial":
            self.output.status = "completed"
    _log("PIPELINE HOÀN TẤT!")
    total_time = time.time() - pipeline_start
    _log(f"Tổng kết: {len(enhanced.chapters)} chương, tổng thời gian: {total_time:.0f}s")

    # ── Optional media production (images) ──────────────────────────────────
    should_run_media = (
        enable_media
        and self.config.pipeline.image_provider != "none"
    )
    if should_run_media:
        _log("══════ SẢN XUẤT ẢNH ══════")
        layer_start = time.time()
        try:
            await asyncio.to_thread(
                self.media_producer.run,
                draft, enhanced,
                progress_callback=lambda m: _log(m),
            )
            _log(f"Media hoàn tất trong {time.time() - layer_start:.1f}s")
        except Exception as e:
            logger.warning(f"Media production failed: {e}")
            _log(f"Media production lỗi: {e}")

    # Attach raw progress events to output for API consumers
    self.output.progress_events = [e.__dict__ for e in tracker.events]

    # Attach pipeline trace summary (Sprint 1 Task 2)
    try:
        self.output.trace = trace.summary()
        _log(
            f"[TRACE] {trace.trace_id} | {len(trace.calls)} calls | "
            f"{trace.total_tokens()} tokens | ${trace.total_cost():.4f}"
        )
    except Exception as _t_err:
        logger.warning(f"Trace summary failed (non-fatal): {_t_err}")
    clear_trace()
    return self.output


def run_layer1_only(
    self: "PipelineOrchestrator",
    title: str,
    genre: str,
    idea: str,
    style: str,
    num_chapters: int,
    num_characters: int,
    word_count: int,
    progress_callback=None,
) -> StoryDraft:
    """Chỉ chạy Layer 1 (story generation).

    Useful for isolated testing or when the caller wants to inspect
    the raw draft before drama simulation.
    """
    return self.story_gen.generate_full_story(
        title=title, genre=genre, idea=idea, style=style,
        num_chapters=num_chapters, num_characters=num_characters,
        word_count=word_count, progress_callback=progress_callback,
    )


def run_layer2_only(
    self: "PipelineOrchestrator",
    draft: StoryDraft,
    num_sim_rounds: int = 5,
    word_count: int = 2000,
    progress_callback=None,
) -> EnhancedStory:
    """Chỉ chạy Layer 2 trên bản thảo có sẵn.

    Runs analyzer → simulator → enhancer without touching Layer 1 or 3.
    """
    _use_signals = bool(getattr(self.config.pipeline, "l2_use_l1_signals", True))
    _conflict_web = list(getattr(draft, "conflict_web", None) or []) or None if _use_signals else None
    _foreshadowing_plan = list(getattr(draft, "foreshadowing_plan", None) or []) or None if _use_signals else None
    analysis = self.analyzer.analyze(draft, _conflict_web)
    sim_result = self.simulator.run_simulation(
        characters=draft.characters,
        relationships=analysis["relationships"],
        genre=draft.genre,
        num_rounds=num_sim_rounds,
        progress_callback=progress_callback,
        drama_intensity=getattr(self.config.pipeline, "drama_intensity", "cao"),
        conflict_web=_conflict_web,
        foreshadowing_plan=_foreshadowing_plan,
    )
    return self.enhancer.enhance_with_feedback(
        draft=draft, sim_result=sim_result,
        word_count=word_count, progress_callback=progress_callback,
    )
