"""Agent Kiểm Tra Văn Phong - đánh giá tính nhất quán tone, voice, và phong cách viết."""
from models.schemas import AgentReview, PipelineOutput
from pipeline.agents.base_agent import BaseAgent
from pipeline.agents import agent_prompts


class StyleConsistencyAgent(BaseAgent):
    name = "Kiem Tra Van Phong"
    role = "style_consistency"
    goal = "Kiểm tra tính nhất quán về tone, voice, và phong cách viết xuyên suốt truyện"
    layers = [1, 2]
    depends_on: list[str] = ["Chuyen Gia Nhan Vat"]

    def review(self, output: PipelineOutput, layer: int, iteration: int, prior_reviews=None) -> AgentReview:
        chapters_excerpt = self._extract_chapters(output, layer)

        prompt = agent_prompts.STYLE_REVIEW.format(
            chapters_excerpt=chapters_excerpt[:3000],
        )

        result = self.llm.generate_json(
            system_prompt=(
                "Bạn là biên tập viên chuyên về phong cách văn học Việt Nam. "
                "Đánh giá tính nhất quán về tone, giọng văn, và phong cách viết. Trả về JSON."
            ),
            user_prompt=prompt,
            temperature=0.4,
        )
        return self._parse_review_json(result, layer, iteration)

    def _extract_chapters(self, output: PipelineOutput, layer: int) -> str:
        """Extract first 500 chars of first 5 chapters from appropriate story source."""
        # Layer 2: use enhanced chapters; Layer 1: use story draft
        if layer == 2 and output.enhanced_story:
            chapters = output.enhanced_story.chapters
        elif output.story_draft:
            chapters = output.story_draft.chapters
        else:
            return "Không có nội dung để kiểm tra văn phong."

        return "\n\n---\n\n".join(
            f"Chương {c.chapter_number} - {c.title}:\n{c.content[:500]}"
            for c in chapters[:5]
        )
