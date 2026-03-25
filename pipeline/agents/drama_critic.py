"""Agent Nhà Phê Bình Kịch Tính - đánh giá arc căng thẳng và độ hấp dẫn."""
import json
import logging

from models.schemas import AgentReview, DebateEntry, DebateStance, PipelineOutput
from pipeline.agents.base_agent import BaseAgent
from pipeline.agents import agent_prompts

logger = logging.getLogger(__name__)


class DramaCriticAgent(BaseAgent):
    name = "Nha Phe Binh Kich Tinh"
    role = "drama_critic"
    goal = "Đánh giá tension arc, cliffhanger, đa dạng cảm xúc và tích hợp sự kiện kịch tính"
    layers = [2]
    depends_on: list[str] = ["Kiem Soat Vien", "Chuyen Gia Doi Thoai", "Kiem Tra Van Phong"]

    def review(self, output: PipelineOutput, layer: int, iteration: int, prior_reviews=None) -> AgentReview:
        enhanced_chapters, simulation_events = self._extract_data(output)

        prompt = agent_prompts.DRAMA_REVIEW.format(
            enhanced_chapters=enhanced_chapters[:2500],
            simulation_events=simulation_events[:1000],
        )

        result = self.llm.generate_json(
            system_prompt="Bạn là nhà phê bình văn học chuyên về kịch tính. Trả về JSON hợp lệ.",
            user_prompt=prompt,
            temperature=0.4,
        )
        return self._parse_review_json(result, layer, iteration)

    def debate_response(self, story_draft, layer, own_review, all_reviews):
        """Challenge reviews that undervalue drama. LLM-backed with rule-based fallback."""
        try:
            return self._llm_debate(story_draft, own_review, all_reviews)
        except Exception as e:
            logger.warning(f"LLM debate failed, using rule-based fallback: {e}")
            return self._rule_based_debate(story_draft, all_reviews)

    def _llm_debate(self, story_draft, own_review, all_reviews):
        """LLM-powered debate analysis."""
        other_reviews = [
            {"agent_name": r.agent_name, "score": r.score,
             "issues": r.issues, "suggestions": r.suggestions}
            for r in all_reviews if r.agent_name != self.name
        ]
        if not other_reviews:
            return []

        # Extract chapter excerpt from story_draft (handles PipelineOutput or StoryDraft)
        chapter_excerpt = self._get_chapter_excerpt(story_draft)

        prompt = agent_prompts.DRAMA_DEBATE.format(
            own_score=own_review.score,
            own_issues=json.dumps(own_review.issues, ensure_ascii=False),
            own_suggestions=json.dumps(own_review.suggestions, ensure_ascii=False),
            other_reviews_json=json.dumps(other_reviews, ensure_ascii=False, indent=2),
            chapter_excerpt=chapter_excerpt,
        )
        result = self.llm.generate_json(
            system_prompt="Bạn là nhà phê bình kịch tính. Phân tích phản hồi và tranh luận. Trả về JSON hợp lệ.",
            user_prompt=prompt,
            temperature=0.4,
            max_tokens=500,
        )
        return self._parse_debate_llm_response(result, all_reviews)

    def _rule_based_debate(self, story_draft, all_reviews):
        """Fallback: keyword-based challenge detection."""
        entries = []
        low_drama_keywords = ["giảm", "bớt kịch tính", "quá mức", "giảm xung đột"]
        for review in all_reviews:
            if review.agent_name == self.name:
                continue
            for suggestion in review.suggestions:
                if any(kw in suggestion.lower() for kw in low_drama_keywords):
                    entries.append(DebateEntry(
                        agent_name=self.name, round_number=2,
                        stance=DebateStance.CHALLENGE,
                        target_agent=review.agent_name,
                        target_issue=suggestion[:100],
                        reasoning="Drama reduction would harm story tension.",
                    ))
        return entries

    def _extract_data(self, output: PipelineOutput) -> tuple[str, str]:
        enhanced_chapters = "Chưa có chương đã tăng cường."
        simulation_events = "Chưa có sự kiện mô phỏng."

        if output.enhanced_story:
            story = output.enhanced_story
            enhanced_chapters = "\n\n---\n\n".join(
                f"Chương {c.chapter_number} - {c.title}:\n{c.content[:500]}"
                for c in story.chapters[:5]
            )
            if story.enhancement_notes:
                enhanced_chapters += "\n\nGhi chú tăng cường:\n" + "\n".join(
                    f"- {note}" for note in story.enhancement_notes[:5]
                )

        if output.simulation_result:
            sim = output.simulation_result
            events = sim.events
            simulation_events = "\n".join(
                f"[Round {e.round_number}] {e.event_type} (kịch tính: {e.drama_score:.1f}): "
                f"{e.description[:150]}"
                for e in events[:10]
            )
            if sim.drama_suggestions:
                simulation_events += "\n\nGợi ý kịch tính:\n" + "\n".join(
                    f"- {s}" for s in sim.drama_suggestions[:5]
                )

        return enhanced_chapters, simulation_events
