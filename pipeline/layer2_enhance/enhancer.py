"""Tăng cường kịch tính cho truyện dựa trên kết quả mô phỏng."""

import asyncio
import logging
from typing import Optional
from models.schemas import (
    StoryDraft, SimulationResult, EnhancedStory, Chapter, count_words,
)
from services.llm_client import LLMClient
from services import prompts
from services import prompts as prompt_templates
from services.adaptive_prompts import build_adaptive_enhance_prompt
from pipeline.layer2_enhance.genre_drama_rules import get_genre_enhancement_hints
from config import ConfigManager

# Consistency Engine (A-E improvements)
try:
    from pipeline.layer2_enhance.consistency_engine import ConsistencyEngine
    _CONSISTENCY_AVAILABLE = True
except ImportError:
    _CONSISTENCY_AVAILABLE = False

logger = logging.getLogger(__name__)

MAX_REENHANCE_ROUNDS = 2
MIN_DRAMA_SCORE = 0.6


def _build_arc_context(draft, chapter_number: int) -> str:
    """Derive arc waypoint context per character for current chapter."""
    try:
        chars = getattr(draft, "characters", None) or []
        lines: list[str] = []
        for c in chars:
            waypoints = getattr(c, "arc_waypoints", None) or []
            for wp in waypoints:
                wp_dict = wp.model_dump() if hasattr(wp, "model_dump") else wp
                if not isinstance(wp_dict, dict):
                    continue
                ch_range = wp_dict.get("chapter_range") or wp_dict.get("range") or ""
                if ch_range:
                    try:
                        parts = str(ch_range).replace(" ", "").split("-")
                        start, end = int(parts[0]), int(parts[-1])
                        if not (start <= chapter_number <= end):
                            continue
                    except (ValueError, IndexError):
                        pass
                stage = wp_dict.get("stage_name") or wp_dict.get("stage") or ""
                pct = wp_dict.get("progress_pct", 0.0)
                if stage:
                    lines.append(f"- {c.name}: {stage} ({int(float(pct) * 100)}%)")
                    break
        return "\n".join(lines)[:400] if lines else ""
    except Exception:
        return ""


def _extract_pacing_directive(draft, chapter_number: int) -> str:
    if draft is None:
        return ""
    try:
        chapters = list(getattr(draft, "chapters", []) or [])
        for ch in chapters:
            if getattr(ch, "chapter_number", None) == chapter_number:
                return str(getattr(ch, "pacing_adjustment", "") or "")
        ctx = getattr(draft, "context", None)
        if ctx is not None:
            return str(getattr(ctx, "pacing_adjustment", "") or "")
    except Exception:
        pass
    return ""


class StoryEnhancer:
    """Viết lại truyện với tính kịch tích cao hơn."""

    LAYER = 2

    def __init__(self):
        self.llm = LLMClient()
        self._layer_model = self.llm.model_for_layer(self.LAYER)
        self.consistency_engine: Optional["ConsistencyEngine"] = None

    def enhance_chapter(
        self,
        chapter: Chapter,
        sim_result: SimulationResult,
        word_count: int = 2000,
        total_chapters: int = 1,
        genre: str = "",
        draft=None,
    ) -> Chapter:
        """Tăng cường kịch tính cho một chương.

        Args:
            total_chapters: Tổng số chương trong truyện (để phân bổ sự kiện đều).
        """

        # --- Scene-level enhancement (Phase 4) ---
        try:
            from pipeline.layer2_enhance.scene_enhancer import SceneEnhancer
            from pipeline.layer2_enhance.dialogue_subtext import DialogueSubtextAnalyzer
            from pipeline.layer2_enhance.thematic_tracker import ThematicTracker

            _subtext_guidance = ""
            _thematic_guidance = ""

            # Build subtext guidance from psychology + knowledge if available
            if draft and hasattr(draft, "characters") and draft.characters:
                try:
                    _analyzer = DialogueSubtextAnalyzer()
                    _psych_map = getattr(draft, "_psychology_map", {})
                    _knowledge = getattr(draft, "_knowledge_state", {})
                    if _psych_map:
                        _subtext_guidance = _analyzer.generate_subtext_guidance(
                            _psych_map, _knowledge
                        )
                except Exception as _e:
                    logger.debug(f"Subtext guidance failed (non-fatal): {_e}")

            # Build thematic guidance if theme profile is attached to draft
            if draft:
                try:
                    _theme = getattr(draft, "_theme_profile", None)
                    if _theme is None:
                        _tracker = ThematicTracker()
                        _theme = _tracker.extract_theme(draft)
                        draft._theme_profile = _theme  # cache for subsequent chapters
                    if _theme and _theme.central_theme:
                        _tracker = ThematicTracker()
                        _ch_score = _tracker.score_chapter_theme(chapter, _theme)
                        _thematic_guidance = _tracker.generate_thematic_guidance(
                            _theme, _ch_score
                        )
                except Exception as _e:
                    logger.debug(f"Thematic guidance failed (non-fatal): {_e}")

            scene_enhancer = SceneEnhancer()
            _signals_on = True
            try:
                _signals_on = bool(getattr(ConfigManager().load().pipeline, "l2_use_l1_signals", True))
            except Exception:
                pass
            _chapter_summary = None
            _thread_state = None
            _arc_context = ""
            _pacing_directive = ""
            if _signals_on:
                _chapter_summary = getattr(chapter, "structured_summary", None)
                if draft is not None:
                    _thread_state = list(getattr(draft, "open_threads", []) or []) + list(getattr(draft, "resolved_threads", []) or [])
                    _arc_context = _build_arc_context(draft, chapter.chapter_number)
                _pacing_directive = _extract_pacing_directive(draft, chapter.chapter_number)
            # Get consistency constraints if engine is available
            _consistency_constraints = ""
            if self.consistency_engine:
                try:
                    _consistency_constraints = self.consistency_engine.get_constraints_for_chapter(
                        chapter.chapter_number
                    )
                except Exception as _ce:
                    logger.debug(f"Consistency constraints failed: {_ce}")

            return scene_enhancer.enhance_chapter_by_scenes(
                chapter, sim_result, genre, draft,
                subtext_guidance=_subtext_guidance,
                thematic_guidance=_thematic_guidance,
                chapter_summary=_chapter_summary,
                thread_state=_thread_state,
                arc_context=_arc_context,
                pacing_directive=_pacing_directive,
                consistency_constraints=_consistency_constraints,
            )
        except Exception as e:
            logger.warning(
                f"[DEPRECATED blob fallback] Scene-level enhancement failed: {e}. "
                "Using legacy whole-chapter rewrite path — scheduled for removal next sprint."
            )
        # --- End scene-level enhancement ---

        # Lọc sự kiện liên quan đến chương này
        relevant_events = [
            e for e in sim_result.events
            if str(chapter.chapter_number) in e.suggested_insertion
            or not e.suggested_insertion
        ]
        if not relevant_events:
            # Phân bổ đều sự kiện theo tổng số chương
            events_per_chapter = max(1, len(sim_result.events) // max(1, total_chapters))
            start = (chapter.chapter_number - 1) * events_per_chapter
            relevant_events = sim_result.events[start:start + events_per_chapter]

        try:
            from pipeline.layer2_enhance.scene_enhancer import _format_events_with_causality
            events_text = _format_events_with_causality(sim_result)
        except Exception:
            events_text = "\n".join(
                f"- [{e.event_type}] {e.description} "
                f"(nhân vật: {', '.join(e.characters_involved)}, kịch tính: {e.drama_score:.1f})"
                for e in relevant_events[:5]
            ) or "Không có sự kiện cụ thể - tăng cường xung đột nội tâm."

        suggestions_text = "\n".join(
            f"- {s}" for s in sim_result.drama_suggestions[:5]
        ) or "Tăng cường miêu tả cảm xúc và xung đột."

        rel_text = "\n".join(
            f"- {r.character_a} ↔ {r.character_b}: {r.relation_type.value} "
            f"(xung đột: {r.tension:.1f})"
            for r in sim_result.updated_relationships[:10]
        )

        # Build Layer 1 context for preservation
        layer1_context = ""
        if draft:
            parts = []
            if hasattr(draft, "foreshadowing_plan") and draft.foreshadowing_plan:
                seeds = [
                    f"- {f.hint} (Ch{f.plant_chapter}→Ch{f.payoff_chapter})"
                    for f in draft.foreshadowing_plan[:5]
                ]
                if seeds:
                    parts.append("Foreshadowing seeds:\n" + "\n".join(seeds))
            if hasattr(draft, "conflict_web") and draft.conflict_web:
                conflicts = [
                    f"- {c.description} [{c.conflict_type}]"
                    for c in draft.conflict_web[:5]
                ]
                if conflicts:
                    parts.append("Conflict web:\n" + "\n".join(conflicts))
            if hasattr(draft, "macro_arcs") and draft.macro_arcs:
                arcs = [
                    f"- Arc {a.arc_number}: {a.name} (Ch{a.chapter_start}-{a.chapter_end})"
                    for a in draft.macro_arcs[:3]
                ]
                if arcs:
                    parts.append("Macro arcs:\n" + "\n".join(arcs))
            layer1_context = "\n".join(parts) if parts else "Không có dữ liệu Layer 1"
        else:
            layer1_context = "Không có dữ liệu Layer 1"

        genre_hints = get_genre_enhancement_hints(genre, chapter.chapter_number, total_chapters)

        enhance_prompt = prompts.ENHANCE_CHAPTER.format(
            original_chapter=chapter.content[:6000],
            drama_events=events_text,
            suggestions=suggestions_text,
            updated_relationships=rel_text,
            word_count=word_count,
            genre_style=genre or "kịch tính",
            genre_hints=genre_hints,
            strong_points="(sẽ được phân tích trong feedback round)",
            layer1_context=layer1_context,
        )
        enhance_prompt = build_adaptive_enhance_prompt(enhance_prompt, genre)
        enhance_prompt += "\n\n[NHẮC LẠI: Viết hoàn toàn bằng tiếng Việt. Không dùng tiếng Anh hay ngôn ngữ khác.]"

        enhanced_content = self.llm.generate(
            system_prompt=(
                "Bạn là nhà văn tài năng chuyên viết truyện kịch tính bằng tiếng Việt. "
                "BẮT BUỘC: Toàn bộ output phải viết bằng tiếng Việt, không được dùng ngôn ngữ khác."
            ),
            user_prompt=enhance_prompt,
            max_tokens=8192,
            model=self._layer_model,
        )

        return Chapter(
            chapter_number=chapter.chapter_number,
            title=chapter.title,
            content=enhanced_content,
            word_count=count_words(enhanced_content),
            summary=chapter.summary,
        )

    def enhance_story(
        self,
        draft: StoryDraft,
        sim_result: SimulationResult,
        word_count: int = 2000,
        progress_callback=None,
        theme_profile=None,
    ) -> EnhancedStory:
        """Tăng cường kịch tính cho toàn bộ truyện."""

        # Cache theme profile on draft so enhance_chapter can access it
        if theme_profile is not None:
            draft._theme_profile = theme_profile

        def _log(msg):
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)

        # Build consistency engine (A-E improvements)
        _consistency_enabled = True
        try:
            _consistency_enabled = bool(ConfigManager().load().pipeline.l2_consistency_engine)
        except Exception:
            pass
        if _CONSISTENCY_AVAILABLE and _consistency_enabled and self.consistency_engine is None:
            try:
                _log("🔧 Building consistency engine...")
                self.consistency_engine = ConsistencyEngine()
                self.consistency_engine.build_from_draft(draft, progress_callback=_log)
            except Exception as e:
                logger.warning(f"ConsistencyEngine build failed (non-fatal): {e}")
                self.consistency_engine = None

        enhanced = EnhancedStory(
            title=draft.title,
            genre=draft.genre,
            enhancement_notes=[],
        )

        total_chapters = len(draft.chapters)
        max_workers = ConfigManager().llm.max_parallel_workers

        _log(f"✨ Đang tăng cường kịch tính {total_chapters} chương (parallel, {max_workers} workers)...")

        # Migrate from ThreadPoolExecutor + as_completed to asyncio.gather + run_in_executor.
        # enhance_chapter() wraps a blocking LLM call; run_in_executor offloads each to the
        # default thread pool while asyncio.gather dispatches all coroutines concurrently,
        # freeing the event loop between submissions.
        async def _enhance_all() -> dict[int, Chapter]:
            loop = asyncio.get_running_loop()
            chapters_list = list(draft.chapters)

            async def _one(chapter: Chapter) -> tuple[int, Chapter]:
                ch_num = chapter.chapter_number
                try:
                    result = await loop.run_in_executor(
                        None, self.enhance_chapter,
                        chapter, sim_result, word_count, total_chapters, draft.genre, draft,
                    )
                    _log(f"✨ Chương {ch_num} đã tăng cường xong")
                    return ch_num, result
                except Exception as e:
                    logger.warning(f"Lỗi enhance chương {ch_num}: {e}")
                    # Fallback: keep original
                    orig = next(c for c in chapters_list if c.chapter_number == ch_num)
                    return ch_num, orig

            pairs = await asyncio.gather(*[_one(ch) for ch in chapters_list])
            return dict(pairs)

        results = asyncio.run(_enhance_all())

        # Maintain order
        enhanced.chapters = [results[ch.chapter_number] for ch in draft.chapters]

        # Cross-chapter drama curve balancing (#3 improvement)
        _curve_enabled = True
        _curve_type = "rising"
        try:
            cfg = ConfigManager().load().pipeline
            _curve_enabled = bool(getattr(cfg, "l2_drama_curve_balancing", True))
            _curve_type = str(getattr(cfg, "l2_drama_curve_target", "rising"))
        except Exception:
            pass

        if _curve_enabled:
            try:
                from pipeline.layer2_enhance.scene_enhancer import DramaCurveBalancer, SceneEnhancer
                _log("📈 Analyzing drama curve...")

                # Score all chapters to build curve
                scene_enhancer = SceneEnhancer()
                chapter_scores: dict[int, float] = {}
                for ch in enhanced.chapters:
                    try:
                        # Quick drama score using cheap model
                        result = self.llm.generate_json(
                            system_prompt="Đánh giá kịch tính nhanh. Trả về JSON.",
                            user_prompt=f"Đánh giá kịch tính nội dung sau (0-1):\n{ch.content[:2000]}\n\n"
                                        '{"drama_score": 0.6}',
                            temperature=0.2,
                            max_tokens=100,
                            model_tier="cheap",
                        )
                        chapter_scores[ch.chapter_number] = float(result.get("drama_score", 0.5))
                    except Exception:
                        chapter_scores[ch.chapter_number] = 0.5

                # Build curve balancer
                balancer = DramaCurveBalancer(curve_type=_curve_type)
                balancer.set_scores(chapter_scores, total_chapters)
                summary = balancer.get_summary()

                _log(
                    f"📈 Drama curve ({_curve_type}): avg={summary['avg_actual']:.2f} "
                    f"(target={summary['avg_target']:.2f}), {summary['total_adjustments']} adjustments needed"
                )

                # Re-enhance chapters that need curve adjustment
                if summary["total_adjustments"] > 0:
                    _log(f"🔄 Re-enhancing {summary['total_adjustments']} chapters for curve balance...")
                    chapters_to_reenhance = (
                        summary.get("chapters_need_boost", []) +
                        summary.get("chapters_need_reduction", [])
                    )

                    for ch_num in chapters_to_reenhance:
                        try:
                            ch = next(c for c in enhanced.chapters if c.chapter_number == ch_num)
                            orig = next(c for c in draft.chapters if c.chapter_number == ch_num)

                            # Re-enhance with curve directive
                            reenhanced = scene_enhancer.enhance_chapter_by_scenes(
                                chapter=orig,
                                sim_result=sim_result,
                                genre=draft.genre,
                                draft=draft,
                                curve_balancer=balancer,
                            )

                            # Update in enhanced list
                            idx = ch_num - 1
                            if 0 <= idx < len(enhanced.chapters):
                                enhanced.chapters[idx] = reenhanced
                                _log(f"  ✓ Chương {ch_num} curve-adjusted")
                        except Exception as e:
                            logger.warning(f"Curve re-enhance ch{ch_num} failed: {e}")

            except Exception as e:
                logger.warning(f"Drama curve balancing failed (non-fatal): {e}")

        # Enhancement diff tracking (non-fatal)
        try:
            from pipeline.layer2_enhance.enhancement_diff_tracker import track_enhancement_diffs
            track_enhancement_diffs(list(draft.chapters), enhanced.chapters)
        except Exception as e:
            logger.warning(f"Enhancement diff tracking failed (non-fatal): {e}")

        # Consistency validation (A-E improvements)
        if self.consistency_engine:
            _log("🔍 Validating consistency...")
            total_violations = 0
            for orig_ch, enh_ch in zip(draft.chapters, enhanced.chapters):
                try:
                    violations = self.consistency_engine.validate_enhanced_chapter(
                        orig_ch.content or "",
                        enh_ch.content or "",
                        enh_ch.chapter_number,
                    )
                    if violations:
                        total_violations += len(violations)
                        # Attach violations to chapter changelog
                        try:
                            enh_ch.enhancement_changelog = list(
                                getattr(enh_ch, "enhancement_changelog", []) or []
                            )
                            for v in violations:
                                enh_ch.enhancement_changelog.append(
                                    f"[{v.type}:{v.severity}] {v.description}"
                                )
                        except Exception:
                            pass
                except Exception as ve:
                    logger.debug(f"Consistency validation ch{enh_ch.chapter_number} error: {ve}")
            if total_violations > 0:
                _log(f"⚠️ Phát hiện {total_violations} vi phạm nhất quán")
            else:
                _log("✅ Không phát hiện vi phạm nhất quán")

        # Voice preservation enforcement (Phase 6)
        _voice_enabled = True
        try:
            _voice_enabled = bool(ConfigManager().load().pipeline.l2_voice_preservation)
        except Exception:
            pass
        if _voice_enabled:
            try:
                from pipeline.layer2_enhance.voice_fingerprint import (
                    VoiceFingerprintEngine, enforce_voice_preservation,
                )
                _log("🎤 Checking voice preservation...")
                voice_engine = VoiceFingerprintEngine()
                voice_engine.build_from_draft(draft)

                total_reverted = 0
                total_drift = 0.0
                characters = getattr(draft, "characters", []) or []

                for orig_ch, enh_ch in zip(draft.chapters, enhanced.chapters):
                    preserved_content, vp_result = enforce_voice_preservation(
                        voice_engine,
                        orig_ch.content or "",
                        enh_ch.content or "",
                        characters,
                        drift_threshold=0.4,
                        revert_threshold=0.3,
                    )
                    if vp_result.reverted_count > 0:
                        enh_ch.content = preserved_content
                        total_reverted += vp_result.reverted_count
                        # Log to changelog
                        try:
                            enh_ch.enhancement_changelog = list(
                                getattr(enh_ch, "enhancement_changelog", []) or []
                            )
                            enh_ch.enhancement_changelog.append(
                                f"[voice:reverted] {vp_result.reverted_count} dialogue(s)"
                            )
                        except Exception:
                            pass
                    total_drift += vp_result.drift_severity

                avg_drift = total_drift / max(1, len(enhanced.chapters))
                if total_reverted > 0:
                    _log(f"🎤 Voice: {total_reverted} dialogues reverted (avg drift: {avg_drift:.0%})")
                else:
                    _log(f"✅ Voice preserved (avg drift: {avg_drift:.0%})")
            except Exception as e:
                logger.warning(f"Voice preservation failed (non-fatal): {e}")

        # Thread resolution enforcement (Phase 6)
        _thread_enforce_enabled = True
        try:
            _thread_enforce_enabled = bool(ConfigManager().load().pipeline.l2_consistency_threads)
        except Exception:
            pass
        if _thread_enforce_enabled:
            try:
                from pipeline.layer2_enhance.thread_watchdog import (
                    ThreadWatchdog, ThreadResolutionEnforcer, should_enforce_resolution,
                )
                total_chapters = len(enhanced.chapters)
                if should_enforce_resolution(total_chapters, total_chapters):
                    _log("🔗 Checking thread resolution...")
                    watchdog = ThreadWatchdog().load_from_draft(draft)
                    enforcer = ThreadResolutionEnforcer(watchdog)

                    total_forced = 0
                    for ch in enhanced.chapters:
                        if should_enforce_resolution(ch.chapter_number, total_chapters):
                            modified_content, resolutions = enforcer.force_resolution(
                                ch.content or "",
                                ch.chapter_number,
                                total_chapters,
                            )
                            if resolutions:
                                ch.content = modified_content
                                total_forced += len(resolutions)
                                try:
                                    ch.enhancement_changelog = list(
                                        getattr(ch, "enhancement_changelog", []) or []
                                    )
                                    for res in resolutions:
                                        ch.enhancement_changelog.append(
                                            f"[thread:resolved] {res.get('thread', '')[:40]}"
                                        )
                                except Exception:
                                    pass

                    summary = enforcer.get_enforcement_summary()
                    if total_forced > 0:
                        _log(
                            f"🔗 Threads: force-resolved {total_forced}, "
                            f"total {summary['resolved']}/{summary['total_threads']} resolved"
                        )
                    elif summary["unresolved"] > 0:
                        _log(f"⚠️ Threads: {summary['unresolved']} unresolved at story end")
                    else:
                        _log("✅ All threads resolved")
            except Exception as e:
                logger.warning(f"Thread resolution enforcement failed (non-fatal): {e}")

        # Tính điểm kịch tính tổng thể (chuyển từ 0-1 sang 1-5)
        if sim_result.events:
            raw = sum(
                e.drama_score for e in sim_result.events
            ) / len(sim_result.events)
            enhanced.drama_score = round(1.0 + raw * 4.0, 2)  # Map 0-1 → 1-5
        enhanced.enhancement_notes = sim_result.drama_suggestions

        _log(
            f"✅ Layer 2 hoàn tất! Điểm kịch tính: {enhanced.drama_score:.2f}"
        )
        return enhanced

    def _find_weak_chapters(self, enhanced: EnhancedStory) -> list[dict]:
        """Analyze chapters and return detailed weakness info for targeted rewriting."""
        weak = []
        for ch in enhanced.chapters:
            try:
                result = self.llm.generate_json(
                    system_prompt="Đánh giá kịch tính chi tiết. Trả về JSON.",
                    user_prompt=prompt_templates.QUICK_DRAMA_CHECK.format(
                        content=ch.content[:3000],
                    ),
                    temperature=0.2,
                    max_tokens=300,
                    model_tier="cheap",
                )
                score = result.get("drama_score", 0.5)
                if score < MIN_DRAMA_SCORE:
                    weak.append({
                        "chapter_number": ch.chapter_number,
                        "score": score,
                        "weak_points": result.get("weak_points", []),
                        "strong_points": result.get("strong_points", []),
                    })
            except Exception as e:
                logger.debug(f"Drama check failed for ch {ch.chapter_number}: {e}")
        return weak

    def enhance_with_feedback(
        self,
        draft: StoryDraft,
        sim_result: SimulationResult,
        word_count: int = 2000,
        progress_callback=None,
        theme_profile=None,
    ) -> EnhancedStory:
        """Enhance story with iterative feedback — re-enhance weak chapters."""
        def _log(msg):
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)

        # Reset consistency engine for fresh build
        self.consistency_engine = None

        enhanced = self.enhance_story(draft, sim_result, word_count, progress_callback, theme_profile)

        genre = draft.genre if hasattr(draft, 'genre') else ""

        # Log drama_multiplier influence: event scores already incorporate agent multipliers
        # from simulator._apply_escalation. Report average event drama_score as proxy.
        if sim_result.events:
            avg_event_score = sum(e.drama_score for e in sim_result.events) / len(sim_result.events)
            logger.info(
                f"Drama multiplier influence: avg event drama_score={avg_event_score:.3f} "
                f"across {len(sim_result.events)} events (agent multipliers embedded)"
            )

        for round_num in range(1, MAX_REENHANCE_ROUNDS + 1):
            weak_analyses = self._find_weak_chapters(enhanced)
            if not weak_analyses:
                _log(f"✅ Feedback round {round_num}: all chapters pass drama threshold")
                break
            _log(f"🔄 Feedback round {round_num}: re-enhancing {len(weak_analyses)} weak chapters (targeted)")
            for analysis in weak_analyses:
                ch_num = analysis["chapter_number"]
                idx = ch_num - 1
                if 0 <= idx < len(enhanced.chapters):
                    # Targeted rewriting with specific weak/strong points
                    genre_hints = get_genre_enhancement_hints(genre, ch_num, len(enhanced.chapters))
                    weak_text = "\n".join(f"- {wp}" for wp in analysis.get("weak_points", []))
                    strong_text = "\n".join(f"- {sp}" for sp in analysis.get("strong_points", []))

                    rewrite_prompt = prompt_templates.REENHANCE_CHAPTER.format(
                        chapter_content=enhanced.chapters[idx].content[:6000],
                        weak_points=weak_text or "Kịch tính chung còn yếu",
                        strong_points=strong_text or "Không có điểm mạnh nổi bật",
                        genre_hints=genre_hints,
                        suggestions="\n".join(sim_result.drama_suggestions[:3]),
                        word_count=word_count,
                    )
                    rewrite_prompt += "\n\n[NHẮC LẠI: Viết hoàn toàn bằng tiếng Việt. Không dùng tiếng Anh hay ngôn ngữ khác.]"
                    rewritten = self.llm.generate(
                        system_prompt=(
                            "Bạn là nhà văn tài năng chuyên viết truyện bằng tiếng Việt. "
                            "BẮT BUỘC: Toàn bộ output phải viết bằng tiếng Việt, không được dùng ngôn ngữ khác."
                        ),
                        user_prompt=rewrite_prompt,
                        max_tokens=8192,
                        model=self._layer_model,
                    )
                    enhanced.chapters[idx] = Chapter(
                        chapter_number=ch_num,
                        title=enhanced.chapters[idx].title,
                        content=rewritten,
                        word_count=count_words(rewritten),
                        summary=enhanced.chapters[idx].summary,
                    )
                    _log(f"  ✓ Chương {ch_num}: score {analysis['score']:.2f} → re-enhanced")

        # Coherence validation (non-fatal)
        try:
            from pipeline.layer2_enhance.coherence_validator import validate_coherence, fix_coherence_issues
            _log("🔍 Đang kiểm tra tính nhất quán...")
            issues = validate_coherence(self.llm, enhanced, draft)
            if issues:
                critical_count = sum(1 for i in issues if i.get("severity") == "critical")
                _log(f"⚠️ Phát hiện {len(issues)} vấn đề nhất quán ({critical_count} critical)")
                if critical_count > 0:
                    fixed = fix_coherence_issues(self.llm, enhanced, issues, word_count)
                    _log(f"✅ Đã sửa {fixed} chương có vấn đề critical")
            else:
                _log("✅ Không phát hiện vấn đề nhất quán")
        except Exception as e:
            logger.warning(f"Coherence validation failed (non-fatal): {e}")

        # Causal audit (Phase B, non-fatal, feature-flagged)
        try:
            _audit_on = bool(getattr(ConfigManager().load().pipeline, "l2_causal_audit", True))
        except Exception:
            _audit_on = True
        if _audit_on:
            try:
                _kr = getattr(draft, "_knowledge_registry", None)
                _cg = getattr(draft, "_causal_graph", None)
                if _kr is not None:
                    from pipeline.layer2_enhance.causal_chain import audit_revelation_causality
                    _log("🔎 Đang kiểm tra nhân quả tiết lộ...")
                    violations = audit_revelation_causality(
                        self.llm, _cg, _kr, enhanced.chapters, enabled=True,
                    )
                    if violations:
                        by_ch: dict[int, list[dict]] = {}
                        for v in violations:
                            by_ch.setdefault(v["chapter_number"], []).append(v)
                        for ch in enhanced.chapters:
                            flags = by_ch.get(ch.chapter_number, [])
                            if not flags:
                                continue
                            try:
                                ch.enhancement_changelog = list(getattr(ch, "enhancement_changelog", []) or [])
                                for v in flags:
                                    ch.enhancement_changelog.append(f"[causality:{v['severity']}] {v['msg']}")
                            except Exception:
                                pass
                        try:
                            object.__setattr__(enhanced, "_causality_flags", violations)
                        except Exception:
                            pass
                        _log(f"⚠️ Nhân quả: {len(violations)} vi phạm trên {len(by_ch)} chương")
                    else:
                        _log("✅ Nhân quả tiết lộ hợp lệ")
            except Exception as e:
                logger.warning(f"Causal audit failed (non-fatal): {e}")

        # Contract gate (Phase E, non-fatal, feature-flagged)
        try:
            _gate_on = bool(getattr(ConfigManager().load().pipeline, "l2_contract_gate", True))
        except Exception:
            _gate_on = True
        if _gate_on:
            try:
                from pipeline.layer2_enhance.contract_gate import apply_contract_gate
                _draft_threads = list(getattr(draft, "open_threads", []) or []) + list(getattr(draft, "resolved_threads", []) or [])
                _log("📋 Đang kiểm tra hợp đồng chương...")
                stats = apply_contract_gate(self.llm, enhanced, _draft_threads, enabled=True)
                if stats.get("rewrites", 0) > 0:
                    _log(
                        f"🔧 Contract gate: {stats['rewrites']} chương viết lại "
                        f"(tổng {stats.get('total_failures', 0)} vi phạm)"
                    )
                else:
                    _log(f"✅ Contract gate: {stats.get('total_failures', 0)} vi phạm, không cần viết lại")
            except Exception as e:
                logger.warning(f"Contract gate failed (non-fatal): {e}")

        # Final consistency report (unresolved threads)
        if self.consistency_engine:
            try:
                report = self.consistency_engine.get_final_report()
                if report.unresolved_threads:
                    _log(f"⚠️ Còn {len(report.unresolved_threads)} tuyến truyện chưa giải quyết")
                    try:
                        enhanced.enhancement_notes = list(enhanced.enhancement_notes or [])
                        for ut in report.unresolved_threads[:5]:
                            enhanced.enhancement_notes.append(
                                f"[UNRESOLVED] {ut.get('description', '')[:80]}"
                            )
                    except Exception:
                        pass
                else:
                    _log("✅ Tất cả tuyến truyện đã được giải quyết")
            except Exception as e:
                logger.debug(f"Final consistency report failed: {e}")

        return enhanced
