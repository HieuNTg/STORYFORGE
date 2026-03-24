"""Agent Phân Tích Nhịp Truyện - đánh giá nhịp điệu, tốc độ hành động, cân bằng hành động/đối thoại."""
import json
from models.schemas import AgentReview, PipelineOutput
from pipeline.agents.base_agent import BaseAgent
from pipeline.agents import agent_prompts
from services.story_analytics import StoryAnalytics


class PacingAnalyzerAgent(BaseAgent):
    name = "Phan Tich Nhip Truyen"
    role = "pacing_analyzer"
    goal = "Phân tích nhịp điệu truyện — tốc độ hành động, chiều dài scene, cân bằng hành động/đối thoại"
    layers = [1, 2]

    def review(self, output: PipelineOutput, layer: int, iteration: int) -> AgentReview:
        pacing_data = self._extract_pacing_data(output, layer)

        prompt = agent_prompts.PACING_REVIEW.format(
            pacing_data=pacing_data,
        )

        result = self.llm.generate_json(
            system_prompt=(
                "Bạn là chuyên gia phân tích nhịp điệu truyện. "
                "Đánh giá pacing dựa trên dữ liệu thống kê. Trả về JSON."
            ),
            user_prompt=prompt,
            temperature=0.4,
        )
        return self._parse_review_json(result, layer, iteration)

    def _extract_pacing_data(self, output: PipelineOutput, layer: int) -> str:
        """Use StoryAnalytics to get pacing metrics for the appropriate story layer."""
        story = None
        if layer == 2 and output.enhanced_story:
            story = output.enhanced_story
        elif output.story_draft:
            story = output.story_draft

        if story is None:
            return "Không có dữ liệu truyện để phân tích nhịp điệu."

        analytics = StoryAnalytics.analyze_story(story)
        pacing = analytics.get("pacing_data", {})

        # Build a human-readable summary for the LLM
        lines = [
            f"Tổng số chương: {analytics.get('total_chapters', 0)}",
            f"Tổng số từ: {analytics.get('total_words', 0)}",
            f"Trung bình từ/chương: {analytics.get('avg_words_per_chapter', 0)}",
            f"Tỷ lệ đối thoại tổng thể: {analytics.get('dialogue_ratio', 0):.2f}",
            "",
            "Chi tiết từng chương (chapter_number | word_count | dialogue_ratio):",
        ]

        chapter_numbers = pacing.get("chapter_numbers", [])
        word_counts = pacing.get("word_counts", [])
        dialogue_ratios = pacing.get("dialogue_ratios", [])

        for i, ch_num in enumerate(chapter_numbers):
            wc = word_counts[i] if i < len(word_counts) else 0
            dr = dialogue_ratios[i] if i < len(dialogue_ratios) else 0.0
            lines.append(f"  Chương {ch_num}: {wc} từ, tỷ lệ thoại={dr:.2f}")

        return "\n".join(lines)
