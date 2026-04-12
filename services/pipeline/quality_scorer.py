"""Quality scoring service - LLM-as-judge for story chapters."""

import asyncio
import logging
from statistics import mean

from models.schemas import Chapter, ChapterScore, StoryScore
from services.llm_client import LLMClient
from services import prompts
from services.text_utils import excerpt_text

logger = logging.getLogger(__name__)


class QualityScorer:
    """Score story chapters on coherence, character consistency, drama, writing quality."""

    def __init__(self):
        self.llm = LLMClient()

    def score_chapter(self, chapter: Chapter, context: str = "") -> ChapterScore:
        """Score a single chapter using cheap model."""
        content = excerpt_text(chapter.content)

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
            thematic_alignment=_clamp(result.get("thematic_alignment", 0), 0.0, 5.0),
            dialogue_depth=_clamp(result.get("dialogue_depth", 0), 0.0, 5.0),
            notes=str(result.get("notes", "")),
        )
        score.overall = (score.coherence + score.character_consistency +
                         score.drama + score.writing_quality) / 4
        return score

    def score_story(self, chapters: list[Chapter], layer: int = 1) -> StoryScore:
        """Score all chapters with rolling context, return aggregate StoryScore.

        Uses asyncio.gather + run_in_executor for concurrent LLM scoring while
        keeping the public API synchronous (safe to call from threads or sync code).
        Context is built sequentially before dispatch so each chapter gets the
        previous chapter's tail as coherence context.
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

        # Score in parallel via asyncio.gather — releases the event loop between
        # LLM calls instead of tying up OS threads per concurrent.futures workers.
        async def _score_all() -> list[ChapterScore]:
            loop = asyncio.get_running_loop()
            results: list[ChapterScore] = []

            async def _score_one(ch: Chapter, ctx: str) -> ChapterScore:
                try:
                    return await loop.run_in_executor(None, self.score_chapter, ch, ctx)
                except Exception as e:
                    logger.warning(f"Scoring chapter {ch.chapter_number} failed: {e}")
                    return ChapterScore(chapter_number=ch.chapter_number)

            results = await asyncio.gather(*[_score_one(ch, ctx) for ch, ctx in tasks])
            return list(results)

        scores: list[ChapterScore] = asyncio.run(_score_all())
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
