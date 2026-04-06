"""Smart Chapter Revision — auto-detect and fix weak chapters using agent reviews."""

import logging
import re

from models.schemas import AgentReview, Chapter, EnhancedStory, StoryScore
from services.llm_client import LLMClient
from services.pipeline.quality_scorer import QualityScorer
from services import prompts

logger = logging.getLogger(__name__)

# Minimum score improvement to accept a revision (validated decision: +0.3)
MIN_IMPROVEMENT_DELTA = 0.3


class SmartRevisionService:
    """Revise weak chapters using quality scores + agent review guidance."""

    def __init__(self, threshold: float = 3.5, max_passes: int = 2):
        self.llm = LLMClient()
        self.scorer = QualityScorer()
        self.threshold = threshold
        self.max_passes = max_passes

    def revise_weak_chapters(
        self,
        enhanced_story: EnhancedStory,
        quality_scores: list[StoryScore],
        reviews: list[AgentReview],
        genre: str = "",
        progress_callback=None,
    ) -> dict:
        """Find weak chapters and revise them with agent review guidance.

        Returns dict with revised_count, total_weak, score_deltas.
        """
        def _log(msg):
            if progress_callback:
                progress_callback(msg)

        # Get latest quality scores
        if not quality_scores:
            _log("Không có điểm chất lượng, bỏ qua revision.")
            return {"revised_count": 0, "total_weak": 0, "score_deltas": []}

        latest_scores = quality_scores[-1]
        if not latest_scores.chapter_scores:
            _log("Không có điểm theo chương, bỏ qua revision.")
            return {"revised_count": 0, "total_weak": 0, "score_deltas": []}

        # Find weak chapters
        weak_scores = [
            cs for cs in latest_scores.chapter_scores
            if cs.overall < self.threshold
        ]

        if not weak_scores:
            _log("Tất cả chương đạt chuẩn, không cần sửa.")
            return {"revised_count": 0, "total_weak": 0, "score_deltas": []}

        _log(f"Tìm thấy {len(weak_scores)} chương yếu (< {self.threshold}/5)")

        # Build chapter lookup
        chapter_map = {c.chapter_number: c for c in enhanced_story.chapters}

        revised_count = 0
        score_deltas = []

        for cs in weak_scores:
            chapter = chapter_map.get(cs.chapter_number)
            if not chapter:
                continue

            issues, suggestions = self._aggregate_review_guidance(cs.chapter_number, reviews)
            old_score = cs.overall

            revised = False
            for pass_num in range(1, self.max_passes + 1):
                _log(f"Chương {cs.chapter_number}: lần thứ {pass_num}/{self.max_passes} (điểm hiện tại: {old_score:.1f})")

                # Build revision prompt
                prompt = prompts.SMART_REVISE_CHAPTER.format(
                    chapter_number=chapter.chapter_number,
                    title=chapter.title,
                    content=chapter.content,
                    issues="\n".join(f"- {i}" for i in issues) if issues else "Không có vấn đề cụ thể.",
                    suggestions="\n".join(f"- {s}" for s in suggestions) if suggestions else "Không có gợi ý cụ thể.",
                    genre=genre or "Chưa xác định",
                    word_count=chapter.word_count or len(chapter.content.split()),
                )

                try:
                    revised_content = self.llm.generate(
                        system_prompt="Bạn là nhà văn chuyên nghiệp. Viết lại chương theo yêu cầu.",
                        user_prompt=prompt,
                        temperature=0.7,
                    )
                except Exception as e:
                    logger.warning(f"LLM revision failed for chapter {cs.chapter_number}: {e}")
                    break

                if not revised_content or len(revised_content.strip()) < 50:
                    logger.warning(f"Revision too short for chapter {cs.chapter_number}, skipping")
                    break

                # Re-score the revised chapter
                temp_chapter = Chapter(
                    chapter_number=chapter.chapter_number,
                    title=chapter.title,
                    content=revised_content,
                    word_count=len(revised_content.split()),
                )
                try:
                    new_score_obj = self.scorer.score_chapter(temp_chapter)
                    new_score = new_score_obj.overall
                except Exception as e:
                    logger.warning(f"Re-scoring failed for chapter {cs.chapter_number}: {e}")
                    break

                delta = new_score - old_score
                _log(f"Chương {cs.chapter_number}: điểm mới {new_score:.1f} (delta: {delta:+.1f})")

                if delta >= MIN_IMPROVEMENT_DELTA:
                    # Accept revision
                    chapter.content = revised_content
                    chapter.word_count = len(revised_content.split())
                    score_deltas.append({
                        "chapter": cs.chapter_number,
                        "old_score": round(old_score, 2),
                        "new_score": round(new_score, 2),
                        "delta": round(delta, 2),
                        "passes": pass_num,
                    })
                    revised = True
                    break
                else:
                    _log(f"Chương {cs.chapter_number}: lần {pass_num} cải thiện không đủ ({delta:+.1f} < +{MIN_IMPROVEMENT_DELTA}), thử lại...")

            if revised:
                revised_count += 1

        _log(f"Hoàn tất: đã sửa {revised_count}/{len(weak_scores)} chương yếu")
        return {
            "revised_count": revised_count,
            "total_weak": len(weak_scores),
            "score_deltas": score_deltas,
        }

    def _aggregate_review_guidance(
        self, chapter_number: int, reviews: list[AgentReview]
    ) -> tuple[list[str], list[str]]:
        """Collect relevant issues and suggestions for a specific chapter.

        Returns (issues, suggestions) capped at 5 each.
        """
        issues = []
        suggestions = []
        # Word-boundary regex to avoid false positives (e.g. "1" matching "chương 10")
        ch_pattern = re.compile(
            rf'\bch(?:ương\s*)?{chapter_number}\b', re.IGNORECASE
        )

        def _mentions_chapter(text: str) -> bool:
            return bool(ch_pattern.search(text))

        for review in reviews:
            # Chapter-specific: mentions this chapter number
            for issue in review.issues:
                if _mentions_chapter(issue):
                    issues.append(f"[{review.agent_name}] {issue}")
            for suggestion in review.suggestions:
                if _mentions_chapter(suggestion):
                    suggestions.append(f"[{review.agent_name}] {suggestion}")

            # General issues from low-scoring agents (not chapter-specific)
            if review.score < 0.6:
                for issue in review.issues:
                    if not _mentions_chapter(issue) and len(issues) < 5:
                        issues.append(f"[{review.agent_name}] {issue}")
                for suggestion in review.suggestions:
                    if not _mentions_chapter(suggestion) and len(suggestions) < 5:
                        suggestions.append(f"[{review.agent_name}] {suggestion}")

        return issues[:5], suggestions[:5]
