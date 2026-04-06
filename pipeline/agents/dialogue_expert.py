"""Agent Chuyên Gia Đối Thoại - đánh giá chất lượng lời thoại."""
from models.schemas import AgentReview, PipelineOutput
from pipeline.agents.base_agent import BaseAgent
from pipeline.agents import agent_prompts


class DialogueExpertAgent(BaseAgent):
    name = "Chuyên Gia Đối Thoại"
    role = "dialogue_expert"
    goal = "Đánh giá tính tự nhiên, giọng nhân vật, và chất lượng tiếng Việt trong đối thoại"
    layers = [2, 3]
    depends_on: list[str] = ["Chuyên Gia Nhân Vật"]

    def review(self, output: PipelineOutput, layer: int, iteration: int, prior_reviews=None) -> AgentReview:
        chapters_content = self._extract_chapters(output, layer)

        prompt = agent_prompts.DIALOGUE_REVIEW.format(
            chapters_content=chapters_content[:3500],
        )

        result = self.llm.generate_json(
            system_prompt="Bạn là chuyên gia viết đối thoại tiếng Việt. Trả về JSON hợp lệ.",
            user_prompt=prompt,
            temperature=0.3,
        )
        return self._parse_review_json(result, layer, iteration)

    def _extract_chapters(self, output: PipelineOutput, layer: int) -> str:
        # Layer 2: enhanced story
        if layer == 2 and output.enhanced_story:
            return "\n\n---\n\n".join(
                f"Chương {c.chapter_number} - {c.title}:\n{c.content[:600]}"
                for c in output.enhanced_story.chapters[:4]
            )

        # Fallback: story draft
        if output.story_draft:
            return "\n\n---\n\n".join(
                f"Chương {c.chapter_number} - {c.title}:\n{c.content[:600]}"
                for c in output.story_draft.chapters[:4]
            )

        return "Không có nội dung để đánh giá đối thoại."
