"""Agent Biên Tập Trưởng - đánh giá tổng thể và tổng hợp review của các agent khác."""
from models.schemas import AgentReview, PipelineOutput
from pipeline.agents.base_agent import BaseAgent
from pipeline.agents import agent_prompts


class EditorInChiefAgent(BaseAgent):
    name = "Bien Tap Truong"
    role = "editor_in_chief"
    goal = "Đánh giá chất lượng tổng thể và tổng hợp phản hồi từ các chuyên gia"
    layers = [1, 2, 3]

    def review(self, output: PipelineOutput, layer: int, iteration: int) -> AgentReview:
        # Tổng hợp reviews từ các agent khác cùng layer (trừ chính mình)
        other_reviews = [
            r for r in output.reviews
            if r.layer == layer and r.agent_role != self.role
        ]

        # Kiểm tra điều kiện tự động từ chối
        if other_reviews:
            scores = [r.score for r in other_reviews]
            avg_score = sum(scores) / len(scores)
            has_critical = any(s < 0.4 for s in scores)

            if has_critical or avg_score < 0.6:
                # Tạo review từ chối dựa trên logic, không cần gọi LLM
                issues = []
                for r in other_reviews:
                    if r.score < 0.6:
                        issues.append(
                            f"{r.agent_name} (điểm {r.score:.1f}): "
                            + "; ".join(r.issues[:2])
                        )
                return AgentReview(
                    agent_role=self.role,
                    agent_name=self.name,
                    score=min(avg_score, 0.55),
                    issues=issues or ["Chất lượng tổng thể chưa đạt yêu cầu"],
                    suggestions=["Cần xem xét lại các vấn đề từ chuyên gia trước"],
                    approved=False,
                    layer=layer,
                    iteration=iteration,
                )

        # Lấy nội dung phù hợp theo layer
        content = self._get_content_for_layer(output, layer)

        # Tóm tắt reviews của các agent khác
        other_reviews_summary = "\n".join(
            f"- {r.agent_name} (điểm {r.score:.1f}): {'; '.join(r.issues[:2]) or 'Không có vấn đề'}"
            for r in other_reviews
        ) or "Chưa có đánh giá từ chuyên gia khác."

        prompt = agent_prompts.EDITOR_REVIEW.format(
            content=content[:3000],
            other_reviews=other_reviews_summary,
        )

        result = self.llm.generate_json(
            system_prompt="Bạn là biên tập viên chuyên nghiệp. Trả về JSON hợp lệ.",
            user_prompt=prompt,
            temperature=0.3,
        )
        return self._parse_review_json(result, layer, iteration)

    def _get_content_for_layer(self, output: PipelineOutput, layer: int) -> str:
        if layer == 1 and output.story_draft:
            draft = output.story_draft
            chapters_preview = "\n\n".join(
                f"Chương {c.chapter_number}: {c.title}\n{c.content[:300]}"
                for c in draft.chapters[:3]
            )
            return f"Tiêu đề: {draft.title}\nThể loại: {draft.genre}\n\n{chapters_preview}"
        if layer == 2 and output.enhanced_story:
            story = output.enhanced_story
            chapters_preview = "\n\n".join(
                f"Chương {c.chapter_number}: {c.title}\n{c.content[:300]}"
                for c in story.chapters[:3]
            )
            return f"Tiêu đề: {story.title}\nĐiểm kịch tính: {story.drama_score}\n\n{chapters_preview}"
        if layer == 3 and output.video_script:
            script = output.video_script
            panels_preview = "\n".join(
                f"Panel {p.panel_number}: {p.description[:100]}"
                for p in script.panels[:5]
            )
            return f"Kịch bản: {script.title}\nTổng thời lượng: {script.total_duration_seconds}s\n\n{panels_preview}"
        return "Chưa có nội dung cho layer này."
