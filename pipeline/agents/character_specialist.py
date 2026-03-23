"""Agent Chuyên Gia Nhân Vật - kiểm tra tính nhất quán của nhân vật."""
from models.schemas import AgentReview, PipelineOutput
from pipeline.agents.base_agent import BaseAgent
from pipeline.agents import agent_prompts


class CharacterSpecialistAgent(BaseAgent):
    name = "Chuyen Gia Nhan Vat"
    role = "character_specialist"
    goal = "Kiểm tra tính nhất quán của nhân vật: tên, tính cách, động lực, mối quan hệ"
    layers = [1, 2]

    def review(self, output: PipelineOutput, layer: int, iteration: int) -> AgentReview:
        # Lấy danh sách nhân vật và nội dung chương theo layer
        characters_info, chapters_content = self._extract_data(output, layer)

        prompt = agent_prompts.CHARACTER_REVIEW.format(
            characters=characters_info,
            chapters_content=chapters_content[:3000],
        )

        result = self.llm.generate_json(
            system_prompt="Bạn là chuyên gia phân tích nhân vật. Trả về JSON hợp lệ.",
            user_prompt=prompt,
            temperature=0.3,
        )
        return self._parse_review_json(result, layer, iteration)

    def _extract_data(self, output: PipelineOutput, layer: int) -> tuple[str, str]:
        # Lấy nhân vật từ story_draft (luôn có ở layer 1 và 2)
        characters_info = "Không có thông tin nhân vật."
        chapters_content = "Không có nội dung chương."

        if output.story_draft:
            draft = output.story_draft
            chars = draft.characters
            if chars:
                characters_info = "\n".join(
                    f"- {c.name} ({c.role}): {c.personality}. Động lực: {c.motivation}. "
                    f"Quan hệ: {', '.join(c.relationships[:3])}"
                    for c in chars
                )

            # Layer 2: dùng enhanced chapters nếu có, fallback về draft
            chapters = (
                output.enhanced_story.chapters
                if layer == 2 and output.enhanced_story
                else draft.chapters
            )
            chapters_content = "\n\n---\n\n".join(
                f"Chương {c.chapter_number} - {c.title}:\n{c.content[:500]}"
                for c in chapters[:4]
            )

        return characters_info, chapters_content
