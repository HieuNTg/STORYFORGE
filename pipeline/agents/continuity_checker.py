"""Agent Kiểm Soát Viên - phát hiện lỗi liên tục trong câu chuyện."""
from models.schemas import AgentReview, PipelineOutput
from pipeline.agents.base_agent import BaseAgent
from pipeline.agents import agent_prompts


class ContinuityCheckerAgent(BaseAgent):
    name = "Kiểm Soát Viên"
    role = "continuity_checker"
    goal = "Phát hiện lỗi dòng thời gian, luật thế giới, nhân vật chết hồi sinh, địa điểm sai"
    layers = [1, 2, 3]
    depends_on: list[str] = ["Chuyên Gia Nhân Vật"]

    def review(self, output: PipelineOutput, layer: int, iteration: int, prior_reviews=None) -> AgentReview:
        world_setting, chapters_content = self._extract_data(output, layer)

        prompt = agent_prompts.CONTINUITY_REVIEW.format(
            world_setting=world_setting,
            chapters_content=chapters_content[:3000],
        )

        result = self.llm.generate_json(
            system_prompt="Bạn là kiểm soát viên chuyên tìm lỗi liên tục. Trả về JSON hợp lệ.",
            user_prompt=prompt,
            temperature=0.2,
        )
        return self._parse_review_json(result, layer, iteration)

    def _extract_data(self, output: PipelineOutput, layer: int) -> tuple[str, str]:
        world_setting = "Không có thông tin bối cảnh."
        chapters_content = "Không có nội dung chương."

        # Lấy world setting từ story draft
        if output.story_draft and output.story_draft.world:
            world = output.story_draft.world
            world_setting = (
                f"Thế giới: {world.name}\n"
                f"Mô tả: {world.description}\n"
                f"Quy tắc: {'; '.join(world.rules[:5])}\n"
                f"Địa điểm: {', '.join(world.locations[:8])}\n"
                f"Thời đại: {world.era}"
            )

        # Chọn chapters theo layer
        chapters = self._get_chapters_for_layer(output, layer)
        if chapters:
            chapters_content = "\n\n---\n\n".join(
                f"Chương {c.chapter_number} - {c.title}:\n{c.content[:500]}"
                for c in chapters[:5]
            )

        return world_setting, chapters_content

    def _get_chapters_for_layer(self, output: PipelineOutput, layer: int):
        if layer == 2 and output.enhanced_story:
            return output.enhanced_story.chapters
        if output.story_draft:
            return output.story_draft.chapters
        return []
