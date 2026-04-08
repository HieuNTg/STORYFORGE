"""Tăng cường kịch tính cho truyện dựa trên kết quả mô phỏng."""

import asyncio
import logging
from models.schemas import (
    StoryDraft, SimulationResult, EnhancedStory, Chapter, count_words,
)
from services.llm_client import LLMClient
from services import prompts
from services import prompts as prompt_templates
from services.adaptive_prompts import build_adaptive_enhance_prompt
from pipeline.layer2_enhance.genre_drama_rules import get_genre_enhancement_hints
from config import ConfigManager

logger = logging.getLogger(__name__)

MAX_REENHANCE_ROUNDS = 2
MIN_DRAMA_SCORE = 0.6


class StoryEnhancer:
    """Viết lại truyện với tính kịch tích cao hơn."""

    LAYER = 2

    def __init__(self):
        self.llm = LLMClient()
        self._layer_model = self.llm.model_for_layer(self.LAYER)

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
            from pipeline.layer2_enhance.thematic_tracker import ThematicTracker, ThemeProfile

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
            return scene_enhancer.enhance_chapter_by_scenes(
                chapter, sim_result, genre, draft,
                subtext_guidance=_subtext_guidance,
                thematic_guidance=_thematic_guidance,
            )
        except Exception as e:
            logger.warning(f"Scene-level enhancement failed, falling back to blob: {e}")
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

        # Enhancement diff tracking (non-fatal)
        try:
            from pipeline.layer2_enhance.enhancement_diff_tracker import track_enhancement_diffs
            track_enhancement_diffs(list(draft.chapters), enhanced.chapters)
        except Exception as e:
            logger.warning(f"Enhancement diff tracking failed (non-fatal): {e}")

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

        return enhanced
