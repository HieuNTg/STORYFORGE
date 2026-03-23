"""Agent Nhà Phê Bình Kịch Tính - đánh giá arc căng thẳng và độ hấp dẫn."""
from models.schemas import AgentReview, PipelineOutput
from pipeline.agents.base_agent import BaseAgent
from pipeline.agents import agent_prompts


class DramaCriticAgent(BaseAgent):
    name = "Nha Phe Binh Kich Tinh"
    role = "drama_critic"
    goal = "Đánh giá tension arc, cliffhanger, đa dạng cảm xúc và tích hợp sự kiện kịch tính"
    layers = [2]

    def review(self, output: PipelineOutput, layer: int, iteration: int) -> AgentReview:
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
