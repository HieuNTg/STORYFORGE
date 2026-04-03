"""Layer execution methods for the 3-layer pipeline.

This module contains the concrete layer-running logic extracted from
PipelineOrchestrator to keep the main class focused on orchestration
rather than implementation details.
"""

import logging
import time
from typing import TYPE_CHECKING

from models.schemas import EnhancedStory, PipelineOutput, StoryDraft

if TYPE_CHECKING:
    from pipeline.orchestrator import PipelineOrchestrator

logger = logging.getLogger(__name__)


def run_full_pipeline(
    self: "PipelineOrchestrator",
    title: str,
    genre: str,
    idea: str,
    style: str = "Miêu tả chi tiết",
    num_chapters: int = 10,
    num_characters: int = 5,
    word_count: int = 2000,
    num_sim_rounds: int = 5,
    shots_per_chapter: int = 8,
    progress_callback=None,
    stream_callback=None,
    enable_agents: bool = True,
    enable_scoring: bool = True,
    enable_media: bool = False,
) -> PipelineOutput:
    """Chạy toàn bộ pipeline 3 lớp (story gen → drama sim → storyboard).

    Delegates to _run_layer1, _run_layer2, _run_layer3 in sequence.
    Each layer saves a checkpoint on success. Layer 2 failures are
    non-fatal — the pipeline continues with the original draft.
    """

    def _log(msg):
        self.output.logs.append(msg)
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    self.output = PipelineOutput(status="running", current_layer=1)
    self._sync_output()
    draft = None
    enhanced = None
    pipeline_start = time.time()

    from services.progress_tracker import ProgressTracker
    tracker = ProgressTracker(callback=_log)

    # Verify LLM connectivity before spending compute
    from services.llm_client import LLMClient
    ok, msg = LLMClient().check_connection()
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
    self.output.current_layer = 1
    layer_start = time.time()
    try:
        draft = self.story_gen.generate_full_story(
            title=title, genre=genre, idea=idea, style=style,
            num_chapters=num_chapters, num_characters=num_characters,
            word_count=word_count,
            progress_callback=lambda m: _log(f"[L1] {m}"),
            stream_callback=stream_callback,
        )
        self.output.story_draft = draft
        self.output.progress = 0.33
        _log(f"Layer 1 hoàn tất trong {time.time() - layer_start:.1f}s")
        self.checkpoint.save(1)

        # Optional quality scoring
        l1_score = None
        if enable_scoring:
            tracker.scoring_started(1)
            try:
                from services.quality_scorer import QualityScorer
                scorer = QualityScorer()
                l1_score = scorer.score_story(draft.chapters, layer=1)
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
                    draft = self.story_gen.generate_full_story(
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
                        l1_score = scorer.score_story(draft.chapters, layer=1)
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
            analytics = StoryAnalytics.analyze_story(draft)
            self.output.analytics = {"layer1": analytics}
            _log(f"[ANALYTICS] Layer 1: {analytics['total_words']} từ, "
                 f"{analytics['reading_time_minutes']} phút đọc, "
                 f"dialogue: {analytics['dialogue_ratio']:.0%}")
        except Exception as e:
            logger.warning(f"Analytics Layer 1 failed: {e}")

        # Build knowledge graph to track character/location relationships
        try:
            from services.knowledge_graph import StoryKnowledgeGraph
            kg = StoryKnowledgeGraph().build_from_story_draft(draft)
            self.output.knowledge_graph_summary = kg.to_summary()
            _log(f"[KG] Knowledge graph: {kg.node_count()} nodes, {kg.edge_count()} edges")
        except Exception as e:
            logger.warning(f"Knowledge graph build failed: {e}")

        # Multi-agent review panel for Layer 1
        if enable_agents:
            _log("[AGENTS] Phòng ban đang đánh giá Layer 1...")
            try:
                reviews = AgentRegistry().run_review_cycle(
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

    # ── Layer 2: Drama simulation & story enhancement ────────────────────────
    _log("══════ LAYER 2: MÔ PHỎNG TĂNG KỊCH TÍNH ══════")
    self.output.current_layer = 2
    layer_start = time.time()
    try:
        _log("[L2] Đang phân tích cấu trúc truyện...")
        analysis = self.analyzer.analyze(draft)

        _log(f"[L2] Bắt đầu mô phỏng {num_sim_rounds} vòng...")
        sim_result = self.simulator.run_simulation(
            characters=draft.characters,
            relationships=analysis["relationships"],
            genre=genre,
            num_rounds=num_sim_rounds,
            progress_callback=lambda m: _log(f"[L2] {m}"),
        )
        self.output.simulation_result = sim_result

        _log("[L2] Đang viết lại truyện với kịch tính cao hơn...")
        enhanced = self.enhancer.enhance_with_feedback(
            draft=draft, sim_result=sim_result,
            word_count=word_count,
            progress_callback=lambda m: _log(f"[L2] {m}"),
        )
        self.output.enhanced_story = enhanced
        self.output.progress = 0.66
        _log(f"Layer 2 hoàn tất trong {time.time() - layer_start:.1f}s")
        self.checkpoint.save(2)

        # Optional quality scoring for Layer 2
        l2_score = None
        if enable_scoring:
            tracker.scoring_started(2)
            try:
                from services.quality_scorer import QualityScorer
                scorer = QualityScorer()
                l2_score = scorer.score_story(enhanced.chapters, layer=2)
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
                    enhanced = self.enhancer.enhance_with_feedback(
                        draft=draft, sim_result=sim_result,
                        word_count=word_count,
                        progress_callback=lambda m: _log(f"[L2-RETRY] {m}"),
                    )
                    self.output.enhanced_story = enhanced
                    # Re-score after retry
                    try:
                        from services.quality_scorer import QualityScorer
                        scorer = QualityScorer()
                        l2_score = scorer.score_story(enhanced.chapters, layer=2)
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
            analytics = StoryAnalytics.analyze_story(enhanced)
            self.output.analytics["layer2"] = analytics
            _log(f"[ANALYTICS] Layer 2: {analytics['total_words']} từ, "
                 f"{analytics['reading_time_minutes']} phút đọc, "
                 f"dialogue: {analytics['dialogue_ratio']:.0%}")
        except Exception as e:
            logger.warning(f"Analytics Layer 2 failed: {e}")

        # Multi-agent review panel for Layer 2
        if enable_agents:
            _log("[AGENTS] Phòng ban đang đánh giá Layer 2...")
            try:
                reviews = AgentRegistry().run_review_cycle(
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

                revision_result = revisor.revise_weak_chapters(
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
        self.output.enhanced_story = enhanced
        self.output.progress = 0.66
        self.output.status = "partial"
        _log("[WARN] Layer 3 will use unenhanced chapters. Video quality may be lower.")

    if not enhanced or not enhanced.chapters:
        _log("[ERROR] No chapters available for Layer 3. Pipeline stopping.")
        self.output.status = "error"
        return self.output

    # ── Layer 3: Video storyboard generation ────────────────────────────────
    _log("══════ LAYER 3: TẠO KỊCH BẢN VIDEO ══════")
    self.output.current_layer = 3
    layer_start = time.time()
    try:
        video_script = self.storyboard_gen.generate_full_video_script(
            story=enhanced,
            characters=draft.characters,
            shots_per_chapter=shots_per_chapter,
            progress_callback=lambda m: _log(f"[L3] {m}"),
        )
        self.output.video_script = video_script
        self.output.progress = 1.0
        if self.output.status != "partial":
            self.output.status = "completed"
        self.checkpoint.save(3)

        # Multi-agent review panel for Layer 3
        if enable_agents:
            _log("[AGENTS] Phòng ban đang đánh giá Layer 3...")
            try:
                reviews = AgentRegistry().run_review_cycle(
                    self.output, layer=3, max_iterations=3,
                    progress_callback=lambda m: _log(m),
                )
                self.output.reviews.extend(reviews)
            except Exception as e:
                logger.warning(f"Agent review Layer 3 lỗi: {e}")

        _log(f"Layer 3 hoàn tất trong {time.time() - layer_start:.1f}s")
        _log("PIPELINE HOÀN TẤT!")
        total_time = time.time() - pipeline_start
        _log(f"Tổng kết: {len(enhanced.chapters)} chương, "
             f"{len(video_script.panels)} panels video, "
             f"~{video_script.total_duration_seconds / 60:.1f} phút, "
             f"tổng thời gian: {total_time:.0f}s")
    except Exception as e:
        logger.warning(f"Layer 3 thất bại: {e}")
        _log(f"Layer 3 lỗi ({str(e)}), pipeline dừng sau Layer 2.")
        self.output.status = "partial"

    # ── Layer 3.5: Optional media production (images, audio, video) ─────────
    should_run_media = (
        enable_media
        and self.output.video_script
        and self.config.pipeline.image_provider != "none"
    )
    if should_run_media:
        if not self.output.video_script or not self.output.video_script.panels:
            _log("[WARN] No video panels. Skipping Layer 3.5.")
        else:
            _log("══════ LAYER 3.5: SẢN XUẤT ẢNH + AUDIO + VIDEO ══════")
            layer_start = time.time()
            try:
                media = self.media_producer.run(
                    draft, enhanced, self.output.video_script,
                    progress_callback=lambda m: _log(m),
                )
                if media.get("video_path"):
                    _log(f"Video: {media['video_path']}")
                _log(f"Layer 3.5 hoàn tất trong {time.time() - layer_start:.1f}s")
            except Exception as e:
                logger.warning(f"Media production failed: {e}")
                _log(f"Media production lỗi: {e}")

    # Attach raw progress events to output for API consumers
    self.output.progress_events = [e.__dict__ for e in tracker.events]
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
    analysis = self.analyzer.analyze(draft)
    sim_result = self.simulator.run_simulation(
        characters=draft.characters,
        relationships=analysis["relationships"],
        genre=draft.genre,
        num_rounds=num_sim_rounds,
        progress_callback=progress_callback,
    )
    return self.enhancer.enhance_with_feedback(
        draft=draft, sim_result=sim_result,
        word_count=word_count, progress_callback=progress_callback,
    )
