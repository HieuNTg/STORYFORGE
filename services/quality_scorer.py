"""Quality scoring service - LLM-as-judge for story chapters."""

import logging
from statistics import mean
from concurrent.futures import ThreadPoolExecutor

from models.schemas import Chapter, ChapterScore, StoryScore
from services.llm_client import LLMClient
from services import prompts

logger = logging.getLogger(__name__)


class QualityScorer:
    """Score story chapters on coherence, character consistency, drama, writing quality."""

    def __init__(self):
        self.llm = LLMClient()

    def score_chapter(self, chapter: Chapter, context: str = "") -> ChapterScore:
        """Score a single chapter using cheap model."""
        # Use head+tail excerpt for long chapters
        content = chapter.content
        if len(content) > 4000:
            head = 2600
            tail = 1400
            content = content[:head] + "\n...\n" + content[-tail:]

        result = self.llm.generate_json(
            system_prompt="Bạn là chuyên gia đánh giá văn học. Trả về JSON.",
            user_prompt=prompts.SCORE_CHAPTER.format(
                chapter_number=chapter.chapter_number,
                content=content,
                context=context or "Đây là chương đầu tiên.",
            ),
            temperature=0.2,
            max_tokens=500,
            model_tier="cheap",
        )

        # Clamp values to 1-5 range
        def _clamp(val, lo=1.0, hi=5.0):
            try:
                return max(lo, min(hi, float(val)))
            except (TypeError, ValueError):
                return 3.0

        score = ChapterScore(
            chapter_number=chapter.chapter_number,
            coherence=_clamp(result.get("coherence", 3)),
            character_consistency=_clamp(result.get("character_consistency", 3)),
            drama=_clamp(result.get("drama", 3)),
            writing_quality=_clamp(result.get("writing_quality", 3)),
            notes=str(result.get("notes", "")),
        )
        score.overall = (score.coherence + score.character_consistency +
                         score.drama + score.writing_quality) / 4
        return score

    def score_story(self, chapters: list[Chapter], layer: int = 1) -> StoryScore:
        """Score all chapters with rolling context, return aggregate StoryScore.

        Uses parallel execution but builds context sequentially from previous
        chapter content for coherence checking.
        """
        if not chapters:
            return StoryScore(scoring_layer=layer, weakest_chapter=0)

        # Build (chapter, context) pairs sequentially so each chapter
        # receives the previous chapter's content as context
        tasks: list[tuple[Chapter, str]] = []
        context = ""
        for ch in chapters:
            tasks.append((ch, context))
            context = ch.content[:500]

        # Score in parallel — context is already bound per-chapter
        scores: list[ChapterScore] = []
        workers = min(3, len(chapters))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self.score_chapter, ch, ctx): ch
                for ch, ctx in tasks
            }
            for future in futures:
                try:
                    scores.append(future.result())
                except Exception as e:
                    ch = futures[future]
                    logger.warning(f"Scoring chapter {ch.chapter_number} failed: {e}")
                    scores.append(ChapterScore(chapter_number=ch.chapter_number))

        scores.sort(key=lambda s: s.chapter_number)

        if not scores:
            return StoryScore(scoring_layer=layer, weakest_chapter=0)

        story_score = StoryScore(
            chapter_scores=scores,
            avg_coherence=mean(s.coherence for s in scores),
            avg_character=mean(s.character_consistency for s in scores),
            avg_drama=mean(s.drama for s in scores),
            avg_writing=mean(s.writing_quality for s in scores),
            weakest_chapter=min(scores, key=lambda s: s.overall).chapter_number,
            scoring_layer=layer,
        )
        story_score.overall = (story_score.avg_coherence + story_score.avg_character +
                               story_score.avg_drama + story_score.avg_writing) / 4
        return story_score
