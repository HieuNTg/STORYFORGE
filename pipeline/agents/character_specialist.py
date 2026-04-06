"""Agent Chuyên Gia Nhân Vật - kiểm tra tính nhất quán của nhân vật."""
import json
import logging

from models.schemas import AgentReview, DebateEntry, DebateStance, PipelineOutput
from pipeline.agents.base_agent import BaseAgent
from pipeline.agents import agent_prompts

logger = logging.getLogger(__name__)


class CharacterSpecialistAgent(BaseAgent):
    name = "Chuyên Gia Nhân Vật"
    role = "character_specialist"
    goal = "Kiểm tra tính nhất quán của nhân vật: tên, tính cách, động lực, mối quan hệ"
    layers = [1, 2]
    depends_on: list[str] = []  # Foundation agent — no dependencies

    def review(self, output: PipelineOutput, layer: int, iteration: int, prior_reviews=None) -> AgentReview:
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

    def debate_response(self, story_draft, layer, own_review, all_reviews):
        """Challenge reviews that sacrifice character consistency. LLM-backed with fallback."""
        try:
            return self._llm_debate(story_draft, own_review, all_reviews)
        except Exception as e:
            logger.warning(f"LLM debate failed, using rule-based fallback: {e}")
            return self._rule_based_debate(all_reviews)

    def _llm_debate(self, story_draft, own_review, all_reviews):
        """LLM-powered debate analysis."""
        other_reviews = [
            {"agent_name": r.agent_name, "score": r.score,
             "issues": r.issues, "suggestions": r.suggestions}
            for r in all_reviews if r.agent_name != self.name
        ]
        if not other_reviews:
            return []

        characters_info = self._get_characters_info(story_draft)
        chapter_excerpt = self._get_chapter_excerpt(story_draft)

        prompt = agent_prompts.CHARACTER_DEBATE.format(
            own_score=own_review.score,
            own_issues=json.dumps(own_review.issues, ensure_ascii=False),
            own_suggestions=json.dumps(own_review.suggestions, ensure_ascii=False),
            other_reviews_json=json.dumps(other_reviews, ensure_ascii=False, indent=2),
            characters_info=characters_info,
            chapter_excerpt=chapter_excerpt,
        )
        result = self.llm.generate_json(
            system_prompt="Bạn là chuyên gia nhân vật. Phân tích phản hồi và tranh luận. Trả về JSON hợp lệ.",
            user_prompt=prompt,
            temperature=0.4,
            max_tokens=500,
        )
        return self._parse_debate_llm_response(result, all_reviews)

    def _rule_based_debate(self, all_reviews):
        """Fallback: keyword-based challenge detection."""
        entries = []
        break_char_keywords = ["thay đổi tính cách", "bất ngờ", "plot twist", "phản bội"]
        for review in all_reviews:
            if review.agent_name == self.name:
                continue
            for issue in review.issues:
                if any(kw in issue.lower() for kw in break_char_keywords):
                    entries.append(DebateEntry(
                        agent_name=self.name, round_number=2,
                        stance=DebateStance.CHALLENGE,
                        target_agent=review.agent_name,
                        target_issue=issue[:100],
                        reasoning="Character behavior change needs proper foreshadowing and motivation buildup.",
                    ))
        return entries

    def _get_characters_info(self, story_draft):
        """Extract character info from PipelineOutput or StoryDraft."""
        draft = getattr(story_draft, 'story_draft', story_draft)
        if not hasattr(draft, 'characters') or not draft.characters:
            return "Không có thông tin nhân vật."
        return "\n".join(
            f"- {c.name} ({c.role}): {c.personality}. Động lực: {c.motivation}"
            for c in draft.characters[:5]
        )

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

    def extract_consistency_context(self, output: PipelineOutput) -> str:
        """Extract character consistency rules for enhancer prompt injection."""
        if not output.story_draft:
            return ""
        draft = output.story_draft
        lines = []
        for c in draft.characters:
            lines.append(f"[{c.name}] Role={c.role}, Tính cách={c.personality}, Động lực={c.motivation}")
            if c.relationships:
                lines.append(f"  Quan hệ: {', '.join(c.relationships[:3])}")
        for s in draft.character_states:
            lines.append(f"[{s.name}] Mood={s.mood}, Arc={s.arc_position}, Last={s.last_action}")
        return "\n".join(lines)
