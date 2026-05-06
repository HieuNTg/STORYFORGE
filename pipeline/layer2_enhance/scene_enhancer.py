"""Scene-Level Enhancement — phân tách chương thành cảnh, chấm điểm, nâng cấp cảnh yếu.

Phase 7 improvements:
- #1: Parallel scene enhancement using asyncio.gather()
- #2: Retry logic for weak scenes after enhancement
- #3: Cross-chapter drama curve balancing
"""

import asyncio
import logging
from typing import Optional
from pydantic import BaseModel, Field
from models.schemas import Chapter, SimulationResult, count_words
from services.llm_client import LLMClient
from services.text_utils import strip_llm_scaffolding, build_idea_header

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# #3: Cross-chapter drama curve balancing
# ─────────────────────────────────────────────────────────────────────────────

class DramaCurveTarget:
    """Target drama curves for different story structures."""
    RISING = "rising"  # Linear increase toward climax
    CLIMAX_AT_END = "climax_at_end"  # Build up to final chapter
    WAVE = "wave"  # Multiple peaks and valleys

    @staticmethod
    def get_target_score(chapter_num: int, total_chapters: int, curve_type: str) -> float:
        """Return target drama score (0-1) for given chapter position."""
        if total_chapters <= 1:
            return 0.7
        progress = chapter_num / total_chapters

        if curve_type == DramaCurveTarget.RISING:
            # Linear increase: 0.4 → 0.9
            return 0.4 + 0.5 * progress

        elif curve_type == DramaCurveTarget.CLIMAX_AT_END:
            # Slow build, sharp rise at end
            if progress < 0.7:
                return 0.4 + 0.2 * (progress / 0.7)
            else:
                return 0.6 + 0.35 * ((progress - 0.7) / 0.3)

        elif curve_type == DramaCurveTarget.WAVE:
            # 3 peaks: 25%, 60%, 95%
            import math
            base = 0.5
            amplitude = 0.3
            # Create wave with peaks at specific points
            wave = math.sin(progress * 3 * math.pi - math.pi / 2)
            return base + amplitude * (wave + 1) / 2

        return 0.6  # Default


class DramaCurveBalancer:
    """Cross-chapter drama curve optimizer (#3 improvement).

    Analyzes drama scores across all chapters and suggests adjustments
    to achieve target curve (rising/climax_at_end/wave).
    """

    def __init__(self, curve_type: str = "rising"):
        self.curve_type = curve_type
        self.chapter_scores: dict[int, float] = {}
        self.target_scores: dict[int, float] = {}
        self.adjustments: dict[int, float] = {}

    def set_scores(self, chapter_scores: dict[int, float], total_chapters: int):
        """Set actual drama scores and compute targets."""
        self.chapter_scores = dict(chapter_scores)
        self.target_scores = {
            ch: DramaCurveTarget.get_target_score(ch, total_chapters, self.curve_type)
            for ch in range(1, total_chapters + 1)
        }
        self._compute_adjustments()

    def _compute_adjustments(self):
        """Compute how much each chapter needs to adjust to match curve."""
        self.adjustments = {}
        for ch, target in self.target_scores.items():
            actual = self.chapter_scores.get(ch, 0.5)
            delta = target - actual
            # Only flag significant deviations (>0.15)
            if abs(delta) > 0.15:
                self.adjustments[ch] = delta

    def get_chapter_adjustment(self, chapter_num: int) -> tuple[float, str]:
        """Return (adjustment_delta, directive) for chapter.

        adjustment_delta: positive = needs more drama, negative = too much drama
        directive: 'escalate' | 'tone_down' | ''
        """
        delta = self.adjustments.get(chapter_num, 0.0)
        if delta > 0.15:
            return delta, "escalate"
        elif delta < -0.15:
            return delta, "tone_down"
        return 0.0, ""

    def get_min_drama_for_chapter(self, chapter_num: int, base_min: float = 0.6) -> float:
        """Adjust minimum drama threshold based on curve target."""
        target = self.target_scores.get(chapter_num, 0.6)
        # Set min_drama slightly below target (allow some tolerance)
        return max(0.3, min(0.85, target - 0.1))

    def get_summary(self) -> dict:
        """Return balancing summary."""
        if not self.chapter_scores:
            return {"status": "not_initialized"}

        avg_actual = sum(self.chapter_scores.values()) / len(self.chapter_scores)
        avg_target = sum(self.target_scores.values()) / len(self.target_scores)
        chapters_need_boost = [ch for ch, d in self.adjustments.items() if d > 0.15]
        chapters_need_reduction = [ch for ch, d in self.adjustments.items() if d < -0.15]

        return {
            "curve_type": self.curve_type,
            "avg_actual": avg_actual,
            "avg_target": avg_target,
            "chapters_need_boost": chapters_need_boost,
            "chapters_need_reduction": chapters_need_reduction,
            "total_adjustments": len(self.adjustments),
        }


def _format_events_with_causality(sim_result: SimulationResult) -> str:
    """Format events as causal chains when available, fall back to flat list."""
    try:
        if sim_result.causal_chains:
            from pipeline.layer2_enhance.causal_chain import CausalGraph
            graph = CausalGraph()
            for event in sim_result.events:
                graph.add_event(event, getattr(event, "cause_event_id", ""))
            text = graph.format_causal_text()
            if text:
                return text
    except Exception:
        pass
    return "\n".join(
        f"- {e.description}" for e in sim_result.events[:5]
    ) or "Không có sự kiện cụ thể."

DECOMPOSE_CHAPTER_CONTENT = """Chia nội dung chương sau thành 3-5 cảnh riêng biệt.
Mỗi cảnh là một đơn vị hành động/đối thoại có ranh giới rõ ràng.

NỘI DUNG CHƯƠNG:
{content}

Trả về JSON:
{{
  "scenes": [
    {{
      "scene_number": 1,
      "content": "nội dung đầy đủ của cảnh",
      "characters_present": ["tên nhân vật"]
    }}
  ]
}}"""

SCORE_SCENE_DRAMA = """Đánh giá kịch tính của cảnh sau (thang 0-1).

THỂ LOẠI: {genre}

NỘI DUNG CẢNH:
{content}

Dữ kiện L1 phải giữ nguyên:
{preserve_facts}

Tiêu chí: xung đột, căng thẳng, cảm xúc mạnh, bước ngoặt, đối thoại sắc bén.

Trả về JSON:
{{
  "drama_score": 0.7,
  "weak_points": ["điểm yếu cụ thể"],
  "strong_points": ["điểm mạnh cụ thể"]
}}"""

ENHANCE_SCENE = """{user_story_idea_header}Viết lại cảnh sau để tăng kịch tính. Giữ nguyên nhân vật và sự kiện chính.

THỂ LOẠI: {genre}
ĐIỂM YẾU CẦN SỬA: {weak_points}
SỰ KIỆN LIÊN QUAN: {events}
HƯỚNG DẪN ĐỐI THOẠI: {subtext_guidance}
HƯỚNG DẪN CHỦ ĐỀ: {thematic_guidance}

DỮ KIỆN L1 PHẢI GIỮ NGUYÊN:
{preserve_facts}

TRẠNG THÁI THREAD:
{thread_status}

VỊ TRÍ ARC NHÂN VẬT:
{arc_context}

{consistency_constraints}

NỘI DUNG GỐC:
{content}

Yêu cầu: thêm căng thẳng, đối thoại sắc bén có chiều sâu tâm lý, cảm xúc mạnh hơn.
KHÔNG mâu thuẫn với dữ kiện L1 hoặc vượt quá vị trí arc hiện tại.
PHẢI giữ nguyên tên riêng / địa danh / gimmick từ [Ý TƯỞNG GỐC] ở đầu prompt — không Việt hoá, không dịch, không thay thế.
Viết hoàn toàn bằng tiếng Việt."""


class SceneScore(BaseModel):
    scene_number: int
    drama_score: float = 0.5
    weak_points: list[str] = Field(default_factory=list)
    strong_points: list[str] = Field(default_factory=list)
    needs_enhancement: bool = False


def _build_preserve_facts(chapter_summary) -> str:
    if not chapter_summary:
        return "Không có"
    try:
        events = getattr(chapter_summary, "key_events", None) or []
        threads = getattr(chapter_summary, "threads_advanced", None) or []
        parts: list[str] = []
        for ev in events[:6]:
            ev_text = str(ev).strip()
            if ev_text:
                parts.append(f"- {ev_text[:160]}")
        for th in threads[:4]:
            th_text = str(th).strip()
            if th_text:
                parts.append(f"[thread] {th_text[:120]}")
        text = "\n".join(parts)
        return text[:800] if text else "Không có"
    except Exception:
        return "Không có"


def _build_thread_status(thread_state) -> str:
    if not thread_state:
        return "Không có"
    try:
        lines: list[str] = []
        for th in list(thread_state)[:8]:
            name = getattr(th, "name", None) or getattr(th, "thread_id", "") or getattr(th, "description", "")
            status = getattr(th, "status", "open")
            urgency = getattr(th, "urgency", 3)
            if name:
                lines.append(f"- {name}: {status} (urgency {urgency}/5)")
        return "\n".join(lines)[:400] or "Không có"
    except Exception:
        return "Không có"


class SceneEnhancer:
    """Phân tách chương thành cảnh, chấm điểm và nâng cấp cảnh yếu.

    Phase 7 improvements:
    - #1: Parallel scene enhancement using asyncio.gather()
    - #2: Retry logic for weak scenes after enhancement
    - #3: Integration with DramaCurveBalancer
    """

    MIN_DRAMA = 0.6

    def __init__(self):
        self.llm = LLMClient()
        # Load config for new features
        try:
            from config import ConfigManager
            cfg = ConfigManager().pipeline
            self.parallel_enabled = getattr(cfg, "l2_parallel_scenes", True)
            self.retry_max = getattr(cfg, "l2_scene_retry_max", 2)
            self.retry_threshold = getattr(cfg, "l2_scene_retry_threshold", 0.5)
        except Exception:
            self.parallel_enabled = True
            self.retry_max = 2
            self.retry_threshold = 0.5

    def decompose_chapter_content(self, chapter: Chapter) -> list[dict]:
        """Dùng LLM chia nội dung chương thành 3-5 cảnh."""
        try:
            result = self.llm.generate_json(
                system_prompt="Phân tách văn bản thành các cảnh. Trả về JSON.",
                user_prompt=DECOMPOSE_CHAPTER_CONTENT.format(content=chapter.content[:5000]),
                temperature=0.2,
                max_tokens=4096,
                model_tier="cheap",
            )
            scenes = result.get("scenes", [])
        except Exception as e:
            logger.warning(f"decompose_chapter_content LLM failed: {e}")
            scenes = []
        if not scenes:
            # Fallback: treat entire chapter as one scene
            return [{"scene_number": 1, "content": chapter.content, "characters_present": []}]
        return scenes

    def score_scenes(
        self,
        scenes: list[dict],
        genre: str,
        preserve_facts: str = "Không có",
        min_drama_override: float | None = None,
    ) -> list[SceneScore]:
        """Chấm điểm kịch tính từng cảnh, đánh dấu cảnh yếu."""
        scores: list[SceneScore] = []
        threshold = min_drama_override if min_drama_override is not None else self.MIN_DRAMA
        for scene in scenes:
            try:
                result = self.llm.generate_json(
                    system_prompt="Đánh giá kịch tính. Trả về JSON.",
                    user_prompt=SCORE_SCENE_DRAMA.format(
                        genre=genre or "kịch tính",
                        content=scene.get("content", "")[:2000],
                        preserve_facts=preserve_facts or "Không có",
                    ),
                    temperature=0.2,
                    max_tokens=300,
                    model_tier="cheap",
                )
                score = SceneScore(
                    scene_number=scene.get("scene_number", 1),
                    drama_score=float(result.get("drama_score", 0.5)),
                    weak_points=result.get("weak_points", []),
                    strong_points=result.get("strong_points", []),
                )
                score.needs_enhancement = score.drama_score < threshold
                scores.append(score)
            except Exception as e:
                logger.debug(f"Score scene {scene.get('scene_number')} failed: {e}")
                scores.append(SceneScore(scene_number=scene.get("scene_number", 1)))
        return scores

    def enhance_weak_scenes(
        self,
        chapter: Chapter,
        scenes: list[dict],
        scores: list[SceneScore],
        sim_result: SimulationResult,
        genre: str,
        subtext_guidance: str = "",
        thematic_guidance: str = "",
        preserve_facts: str = "Không có",
        thread_status: str = "Không có",
        arc_context: str = "Không có",
        consistency_constraints: str = "",
        curve_directive: str = "",
        user_story_idea_header: str = "",
    ) -> Chapter:
        """Nâng cấp cảnh yếu với parallel processing và retry (#1, #2 improvements)."""
        score_map = {s.scene_number: s for s in scores}
        events_text = _format_events_with_causality(sim_result)

        # Identify weak scenes
        weak_scenes = [
            (scene, score_map.get(scene.get("scene_number", 1)))
            for scene in scenes
            if score_map.get(scene.get("scene_number", 1), SceneScore(scene_number=1)).needs_enhancement
        ]

        if not weak_scenes:
            # No weak scenes, return original
            stitched = "\n\n".join(strip_llm_scaffolding(s.get("content", "")) for s in scenes)
            return Chapter(
                chapter_number=chapter.chapter_number,
                title=chapter.title,
                content=stitched,
                word_count=count_words(stitched),
                summary=chapter.summary,
                enhancement_changelog=chapter.enhancement_changelog,
            )

        # Build enhancement context (shared across all scenes)
        enhance_context = {
            "genre": genre or "kịch tính",
            "events": events_text,
            "subtext_guidance": subtext_guidance or "Không có",
            "thematic_guidance": thematic_guidance or "Không có",
            "preserve_facts": preserve_facts or "Không có",
            "thread_status": thread_status or "Không có",
            "arc_context": arc_context or "Không có",
            "consistency_constraints": consistency_constraints or "",
            "curve_directive": curve_directive,
            "user_story_idea_header": user_story_idea_header or "",
        }

        # Choose parallel or sequential based on config
        if self.parallel_enabled and len(weak_scenes) > 1:
            enhanced_map = self._enhance_scenes_parallel(weak_scenes, enhance_context)
        else:
            enhanced_map = self._enhance_scenes_sequential(weak_scenes, enhance_context)

        # Build final chapter content
        enhanced_parts: list[str] = []
        for scene in scenes:
            snum = scene.get("scene_number", 1)
            if snum in enhanced_map:
                enhanced_parts.append(strip_llm_scaffolding(enhanced_map[snum]))
            else:
                enhanced_parts.append(strip_llm_scaffolding(scene.get("content", "")))

        stitched = "\n\n".join(p for p in enhanced_parts if p)
        return Chapter(
            chapter_number=chapter.chapter_number,
            title=chapter.title,
            content=stitched,
            word_count=count_words(stitched),
            summary=chapter.summary,
            enhancement_changelog=chapter.enhancement_changelog,
        )

    def _enhance_scenes_parallel(
        self,
        weak_scenes: list[tuple[dict, SceneScore]],
        context: dict,
    ) -> dict[int, str]:
        """Parallel scene enhancement using asyncio (#1 improvement)."""

        async def _enhance_all():
            loop = asyncio.get_running_loop()

            async def _enhance_one(scene: dict, score: SceneScore) -> tuple[int, str]:
                snum = scene.get("scene_number", 1)
                content = scene.get("content", "")
                try:
                    result = await loop.run_in_executor(
                        None,
                        self._enhance_single_scene_with_retry,
                        scene, score, context,
                    )
                    return snum, result
                except Exception as e:
                    logger.warning(f"Parallel enhance scene {snum} failed: {e}")
                    return snum, content

            pairs = await asyncio.gather(*[
                _enhance_one(scene, score) for scene, score in weak_scenes
            ])
            return dict(pairs)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Already in async context — run in thread pool
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, _enhance_all())
                return future.result()
        else:
            return asyncio.run(_enhance_all())

    def _enhance_scenes_sequential(
        self,
        weak_scenes: list[tuple[dict, SceneScore]],
        context: dict,
    ) -> dict[int, str]:
        """Sequential scene enhancement (fallback)."""
        results = {}
        for scene, score in weak_scenes:
            snum = scene.get("scene_number", 1)
            try:
                results[snum] = self._enhance_single_scene_with_retry(scene, score, context)
            except Exception as e:
                logger.warning(f"Sequential enhance scene {snum} failed: {e}")
                results[snum] = scene.get("content", "")
        return results

    def _enhance_single_scene_with_retry(
        self,
        scene: dict,
        score: SceneScore,
        context: dict,
    ) -> str:
        """Enhance a single scene with retry logic (#2 improvement)."""
        snum = scene.get("scene_number", 1)
        content = scene.get("content", "")
        current_content = content
        current_score = score.drama_score
        weak_points = list(score.weak_points)

        # Add curve directive to weak points if provided
        curve_directive = context.get("curve_directive", "")
        if curve_directive == "escalate":
            weak_points.insert(0, "CẦN TĂNG KỊCH TÍNH (theo curve mục tiêu)")
        elif curve_directive == "tone_down":
            weak_points.insert(0, "CẦN GIẢM NHẸ KỊCH TÍNH (tránh melodrama)")

        for attempt in range(self.retry_max + 1):
            weak_text = "\n".join(f"- {w}" for w in weak_points) or "Kịch tính yếu"

            try:
                new_content = self.llm.generate(
                    system_prompt=(
                        "Bạn là nhà văn tài năng. "
                        "BẮT BUỘC viết toàn bộ bằng tiếng Việt. "
                        "CHỈ trả về văn xuôi của cảnh, KHÔNG thêm lời dẫn, nhãn 'BỐI CẢNH/NHÂN VẬT', "
                        "dấu '***' hay bất kỳ siêu dữ liệu nào."
                    ),
                    user_prompt=ENHANCE_SCENE.format(
                        user_story_idea_header=context.get("user_story_idea_header", ""),
                        genre=context["genre"],
                        weak_points=weak_text,
                        events=context["events"],
                        subtext_guidance=context["subtext_guidance"],
                        thematic_guidance=context["thematic_guidance"],
                        preserve_facts=context["preserve_facts"],
                        thread_status=context["thread_status"],
                        arc_context=context["arc_context"],
                        consistency_constraints=context["consistency_constraints"],
                        content=current_content[:3000],
                    ),
                    max_tokens=4096,
                )
                new_content = strip_llm_scaffolding(new_content)

                # Check if enhanced scene is good enough (re-score)
                if attempt < self.retry_max:
                    try:
                        rescore = self.llm.generate_json(
                            system_prompt="Đánh giá kịch tính. Trả về JSON.",
                            user_prompt=SCORE_SCENE_DRAMA.format(
                                genre=context["genre"],
                                content=new_content[:2000],
                                preserve_facts=context["preserve_facts"],
                            ),
                            temperature=0.2,
                            max_tokens=300,
                            model_tier="cheap",
                        )
                        new_score = float(rescore.get("drama_score", 0.5))

                        if new_score >= self.retry_threshold:
                            logger.debug(
                                f"Scene {snum} enhanced: {current_score:.2f} → {new_score:.2f} "
                                f"(attempt {attempt + 1})"
                            )
                            return new_content

                        # Still weak, prepare for retry
                        logger.info(
                            f"Scene {snum} still weak after enhance: {new_score:.2f} < {self.retry_threshold:.2f}, "
                            f"retry {attempt + 1}/{self.retry_max}"
                        )
                        current_content = new_content
                        current_score = new_score
                        weak_points = rescore.get("weak_points", ["Kịch tính chưa đủ"])

                    except Exception as e:
                        logger.debug(f"Re-score scene {snum} failed, accepting result: {e}")
                        return new_content
                else:
                    # Last attempt, return whatever we have
                    return new_content

            except Exception as e:
                logger.warning(f"Enhance scene {snum} attempt {attempt + 1} failed: {e}")
                if attempt == self.retry_max:
                    return content  # Return original on final failure

        return current_content

    def enhance_chapter_by_scenes(
        self,
        chapter: Chapter,
        sim_result: SimulationResult,
        genre: str,
        draft=None,
        subtext_guidance: str = "",
        thematic_guidance: str = "",
        chapter_summary=None,
        thread_state=None,
        arc_context: str = "",
        pacing_directive: str = "",
        consistency_constraints: str = "",
        curve_balancer: Optional[DramaCurveBalancer] = None,
    ) -> Chapter:
        """Pipeline đầy đủ: phân tách → chấm điểm → nâng cấp cảnh yếu → ghép lại.

        Args:
            curve_balancer: Optional DramaCurveBalancer for cross-chapter optimization (#3)
        """
        summary = chapter_summary  # caller decides whether to pass; None = skip signal reuse
        preserve_facts = _build_preserve_facts(summary)
        thread_text = _build_thread_status(thread_state)
        arc_text = arc_context or "Không có"

        min_drama = self.MIN_DRAMA
        curve_directive = ""

        # L2-E: Per-chapter drama intensity based on pacing_type from outline
        _PACING_DRAMA_TARGETS = {
            "climax": 0.85, "twist": 0.80, "rising": 0.70, "fast": 0.75,
            "setup": 0.45, "cooldown": 0.50, "falling": 0.50, "slow": 0.45,
            "resolution": 0.55, "": 0.60,  # default
        }
        try:
            # Try to get pacing_type from chapter's outline if attached
            _ch_pacing = ""
            if hasattr(chapter, "pacing_type"):
                _ch_pacing = getattr(chapter, "pacing_type", "") or ""
            if not _ch_pacing and pacing_directive:
                # pacing_directive is sometimes the pacing_type
                _ch_pacing = pacing_directive if pacing_directive in _PACING_DRAMA_TARGETS else ""
            if _ch_pacing in _PACING_DRAMA_TARGETS:
                min_drama = _PACING_DRAMA_TARGETS[_ch_pacing]
                logger.debug(f"Ch{chapter.chapter_number}: pacing='{_ch_pacing}' → min_drama={min_drama:.2f}")
        except Exception:
            pass

        # Apply pacing directive adjustments (fine-tuning)
        if pacing_directive == "slow_down":
            min_drama = max(0.3, min_drama - 0.1)
        elif pacing_directive == "escalate":
            min_drama = min(0.9, min_drama + 0.1)

        # Apply curve balancer adjustments (#3 improvement)
        if curve_balancer:
            curve_min = curve_balancer.get_min_drama_for_chapter(chapter.chapter_number, min_drama)
            _, curve_directive = curve_balancer.get_chapter_adjustment(chapter.chapter_number)
            if curve_directive:
                logger.info(
                    f"Chapter {chapter.chapter_number}: curve adjustment '{curve_directive}' "
                    f"(min_drama: {min_drama:.2f} → {curve_min:.2f})"
                )
                min_drama = curve_min

        scenes = self._scenes_from_summary(chapter, summary)
        if not scenes:
            scenes = self.decompose_chapter_content(chapter)
        else:
            logger.info(f"[L2] Chapter {chapter.chapter_number}: structured_summary reused, decompose skipped")

        scores = self.score_scenes(scenes, genre, preserve_facts=preserve_facts, min_drama_override=min_drama)

        weak_count = sum(1 for s in scores if s.needs_enhancement)
        parallel_note = "parallel" if self.parallel_enabled else "sequential"
        logger.info(
            f"Chapter {chapter.chapter_number}: {len(scenes)} scenes, "
            f"{weak_count} need enhancement (min_drama={min_drama:.2f}, mode={parallel_note})"
        )

        if weak_count == 0:
            logger.info(f"Chapter {chapter.chapter_number}: all scenes strong, skipping")
            return chapter

        # Pull author's original idea from draft so L2 enhancement preserves
        # proper nouns / gimmicks instead of pulling story toward genre average.
        _idea_header = ""
        if draft is not None:
            _idea = getattr(draft, "original_idea", "") or ""
            _idea_summary = getattr(draft, "idea_summary_for_chapters", "") or ""
            if _idea:
                _idea_header = build_idea_header(_idea, _idea_summary)

        return self.enhance_weak_scenes(
            chapter, scenes, scores, sim_result, genre,
            subtext_guidance=subtext_guidance,
            thematic_guidance=thematic_guidance,
            preserve_facts=preserve_facts,
            thread_status=thread_text,
            arc_context=arc_text,
            consistency_constraints=consistency_constraints,
            curve_directive=curve_directive,
            user_story_idea_header=_idea_header,
        )

    @staticmethod
    def _scenes_from_summary(chapter: Chapter, summary) -> list[dict]:
        if not summary:
            return []
        try:
            events = getattr(summary, "key_events", None) or []
            if len(events) < 3:
                return []
            content = chapter.content or ""
            if len(content) < 200:
                return []
            n = min(len(events), 5)
            chunk_size = max(1, len(content) // n)
            scenes: list[dict] = []
            for idx in range(n):
                start = idx * chunk_size
                end = start + chunk_size if idx < n - 1 else len(content)
                piece = content[start:end].strip()
                if not piece:
                    continue
                scenes.append({
                    "scene_number": idx + 1,
                    "content": piece,
                    "characters_present": [],
                })
            return scenes if len(scenes) >= 3 else []
        except Exception:
            return []
