"""Agent Cân Bằng Đối Thoại - đánh giá phân bổ đối thoại và giọng riêng từng nhân vật."""
from models.schemas import AgentReview, PipelineOutput
from pipeline.agents.base_agent import BaseAgent
from pipeline.agents import agent_prompts


class DialogueBalanceAgent(BaseAgent):
    name = "Cân Bằng Đối Thoại"
    role = "dialogue_balance"
    goal = "Đánh giá phân bổ đối thoại, giọng nói riêng biệt của từng nhân vật"
    layers = [2]
    depends_on: list[str] = ["Chuyên Gia Đối Thoại"]

    def review(self, output: PipelineOutput, layer: int, iteration: int, prior_reviews=None) -> AgentReview:
        characters, chapters_excerpt = self._extract_data(output)

        prompt = agent_prompts.DIALOGUE_BALANCE_REVIEW.format(
            characters=characters,
            chapters_excerpt=chapters_excerpt[:3000],
        )

        result = self.llm.generate_json(
            system_prompt=(
                "Bạn là chuyên gia đối thoại văn học. "
                "Đánh giá mỗi nhân vật có giọng riêng không. Trả về JSON."
            ),
            user_prompt=prompt,
            temperature=0.4,
        )
        return self._parse_review_json(result, layer, iteration)

    def _extract_data(self, output: PipelineOutput) -> tuple[str, str]:
        """Extract character names from story_draft and dialogues from enhanced chapters."""
        characters = "Không có thông tin nhân vật."
        chapters_excerpt = "Không có nội dung đối thoại."

        # Characters always come from story_draft
        if output.story_draft and output.story_draft.characters:
            characters = "\n".join(
                f"- {c.name} ({c.role}): {c.personality}"
                for c in output.story_draft.characters
            )

        # Dialogues from enhanced story (layer 2 focus)
        if output.enhanced_story:
            chapters = output.enhanced_story.chapters
        elif output.story_draft:
            chapters = output.story_draft.chapters
        else:
            return characters, chapters_excerpt

        chapters_excerpt = "\n\n---\n\n".join(
            f"Chương {c.chapter_number} - {c.title}:\n{c.content[:500]}"
            for c in chapters[:5]
        )

        return characters, chapters_excerpt
