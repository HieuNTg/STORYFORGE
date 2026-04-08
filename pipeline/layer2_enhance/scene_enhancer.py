"""Scene-Level Enhancement — phân tách chương thành cảnh, chấm điểm, nâng cấp cảnh yếu."""

import logging
from pydantic import BaseModel, Field
from models.schemas import Chapter, SimulationResult, count_words
from services.llm_client import LLMClient

logger = logging.getLogger(__name__)

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

NỘI DUNG GỐC:
{content}

Yêu cầu: thêm căng thẳng, đối thoại sắc bén có chiều sâu tâm lý, cảm xúc mạnh hơn.
Viết hoàn toàn bằng tiếng Việt."""


class SceneScore(BaseModel):
    scene_number: int
    drama_score: float = 0.5
    weak_points: list[str] = Field(default_factory=list)
    strong_points: list[str] = Field(default_factory=list)
    needs_enhancement: bool = False


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

    def score_scenes(self, scenes: list[dict], genre: str) -> list[SceneScore]:
        """Chấm điểm kịch tính từng cảnh, đánh dấu cảnh yếu."""
        scores: list[SceneScore] = []
        for scene in scenes:
            try:
                result = self.llm.generate_json(
                    system_prompt="Đánh giá kịch tính. Trả về JSON.",
                    user_prompt=SCORE_SCENE_DRAMA.format(
                        genre=genre or "kịch tính",
                        content=scene.get("content", "")[:2000],
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
                score.needs_enhancement = score.drama_score < self.MIN_DRAMA
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
    ) -> Chapter:
        """Nâng cấp chỉ những cảnh yếu, ghép lại thành chương hoàn chỉnh."""
        score_map = {s.scene_number: s for s in scores}
        events_text = "\n".join(
            f"- {e.description}" for e in sim_result.events[:5]
        ) or "Không có sự kiện cụ thể."

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
    ) -> Chapter:
        """Pipeline đầy đủ: phân tách → chấm điểm → nâng cấp cảnh yếu → ghép lại."""
        scenes = self.decompose_chapter_content(chapter)
        scores = self.score_scenes(scenes, genre)

        weak_count = sum(1 for s in scores if s.needs_enhancement)
        logger.info(
            f"Chapter {chapter.chapter_number}: {len(scenes)} scenes, "
            f"{weak_count} need enhancement"
        )

        if weak_count == 0:
            logger.info(f"Chapter {chapter.chapter_number}: all scenes strong, skipping")
            return chapter

        return self.enhance_weak_scenes(
            chapter, scenes, scores, sim_result, genre,
            subtext_guidance=subtext_guidance,
            thematic_guidance=thematic_guidance,
        )
