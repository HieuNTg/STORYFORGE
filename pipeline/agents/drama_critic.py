"""Agent Nhà Phê Bình Kịch Tính - đánh giá arc căng thẳng và độ hấp dẫn."""
from models.schemas import AgentReview, DebateEntry, DebateStance, PipelineOutput
from pipeline.agents.base_agent import BaseAgent
from pipeline.agents import agent_prompts


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
        """Challenge reviews that undervalue drama or suggest reducing tension."""
        entries = []
        for review in all_reviews:
            if review.agent_name == self.name:
                continue
            # Challenge if another agent suggests reducing drama
            low_drama_keywords = ["giảm", "bớt kịch tính", "quá mức", "giảm xung đột"]
            for suggestion in review.suggestions:
                if any(kw in suggestion.lower() for kw in low_drama_keywords):
                    genre = getattr(story_draft, 'genre', None)
                    if genre is None and hasattr(story_draft, 'story_draft'):
                        genre = getattr(story_draft.story_draft, 'genre', 'unknown')
                    entries.append(DebateEntry(
                        agent_name=self.name,
                        round_number=2,
                        stance=DebateStance.CHALLENGE,
                        target_agent=review.agent_name,
                        target_issue=suggestion[:100],
                        reasoning=(
                            f"Drama reduction would harm story tension. Current drama level "
                            f"is appropriate for {genre}."
                        ),
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
