"""Scene-Level Enhancement — phân tách chương thành cảnh, chấm điểm, nâng cấp cảnh yếu."""

import logging
from pydantic import BaseModel, Field
from models.schemas import Chapter, SimulationResult, count_words
from services.llm_client import LLMClient

logger = logging.getLogger(__name__)


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

ENHANCE_SCENE = """Viết lại cảnh sau để tăng kịch tính. Giữ nguyên nhân vật và sự kiện chính.

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
    """Phân tách chương thành cảnh, chấm điểm và nâng cấp cảnh yếu."""

    MIN_DRAMA = 0.6

    def __init__(self):
        self.llm = LLMClient()

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
    ) -> Chapter:
        """Nâng cấp chỉ những cảnh yếu, ghép lại thành chương hoàn chỉnh."""
        score_map = {s.scene_number: s for s in scores}
        events_text = _format_events_with_causality(sim_result)

        enhanced_parts: list[str] = []
        for scene in scenes:
            snum = scene.get("scene_number", 1)
            content = scene.get("content", "")
            sc = score_map.get(snum)

            if sc and sc.needs_enhancement:
                try:
                    weak_text = "\n".join(f"- {w}" for w in sc.weak_points) or "Kịch tính yếu"
                    new_content = self.llm.generate(
                        system_prompt=(
                            "Bạn là nhà văn tài năng. "
                            "BẮT BUỘC viết toàn bộ bằng tiếng Việt."
                        ),
                        user_prompt=ENHANCE_SCENE.format(
                            genre=genre or "kịch tính",
                            weak_points=weak_text,
                            events=events_text,
                            subtext_guidance=subtext_guidance or "Không có",
                            thematic_guidance=thematic_guidance or "Không có",
                            preserve_facts=preserve_facts or "Không có",
                            thread_status=thread_status or "Không có",
                            arc_context=arc_context or "Không có",
                            consistency_constraints=consistency_constraints or "",
                            content=content[:3000],
                        ),
                        max_tokens=4096,
                    )
                    enhanced_parts.append(new_content)
                    logger.debug(f"Scene {snum} enhanced (was {sc.drama_score:.2f})")
                except Exception as e:
                    logger.warning(f"Enhance scene {snum} failed, keeping original: {e}")
                    enhanced_parts.append(content)
            else:
                enhanced_parts.append(content)

        stitched = "\n\n".join(enhanced_parts)
        return Chapter(
            chapter_number=chapter.chapter_number,
            title=chapter.title,
            content=stitched,
            word_count=count_words(stitched),
            summary=chapter.summary,
            enhancement_changelog=chapter.enhancement_changelog,
        )

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
    ) -> Chapter:
        """Pipeline đầy đủ: phân tách → chấm điểm → nâng cấp cảnh yếu → ghép lại."""
        summary = chapter_summary  # caller decides whether to pass; None = skip signal reuse
        preserve_facts = _build_preserve_facts(summary)
        thread_text = _build_thread_status(thread_state)
        arc_text = arc_context or "Không có"

        min_drama = self.MIN_DRAMA
        if pacing_directive == "slow_down":
            min_drama = max(0.3, self.MIN_DRAMA - 0.1)
        elif pacing_directive == "escalate":
            min_drama = min(0.9, self.MIN_DRAMA + 0.1)

        scenes = self._scenes_from_summary(chapter, summary)
        skip_note = bool(scenes)
        if not scenes:
            scenes = self.decompose_chapter_content(chapter)
        else:
            logger.info(f"[L2] Chapter {chapter.chapter_number}: structured_summary reused, decompose skipped")

        scores = self.score_scenes(scenes, genre, preserve_facts=preserve_facts, min_drama_override=min_drama)

        weak_count = sum(1 for s in scores if s.needs_enhancement)
        logger.info(
            f"Chapter {chapter.chapter_number}: {len(scenes)} scenes, "
            f"{weak_count} need enhancement (min_drama={min_drama:.2f}, skip_decompose={skip_note})"
        )

        if weak_count == 0:
            logger.info(f"Chapter {chapter.chapter_number}: all scenes strong, skipping")
            return chapter

        return self.enhance_weak_scenes(
            chapter, scenes, scores, sim_result, genre,
            subtext_guidance=subtext_guidance,
            thematic_guidance=thematic_guidance,
            preserve_facts=preserve_facts,
            thread_status=thread_text,
            arc_context=arc_text,
            consistency_constraints=consistency_constraints,
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
