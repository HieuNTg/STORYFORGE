"""Base class cho tất cả agent trong phòng ban."""
from abc import ABC, abstractmethod
import logging
from typing import Optional
from models.schemas import AgentReview, DebateEntry, DebateStance, PipelineOutput
from services.llm_client import LLMClient

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Agent cơ sở - mỗi agent đánh giá/cải thiện output ở layer cụ thể."""

    name: str = ""
    role: str = ""
    goal: str = ""
    layers: list[int] = []  # Agent hoạt động ở layer nào (1, 2, 3)
    depends_on: list[str] = []  # Names of agents this agent depends on (DAG edges)

    def __init__(self):
        self.llm = LLMClient()

    @abstractmethod
    def review(
        self,
        output: PipelineOutput,
        layer: int,
        iteration: int,
        prior_reviews: Optional[list[AgentReview]] = None,
    ) -> AgentReview:
        """Đánh giá output hiện tại. Trả về AgentReview.

        Args:
            output: Pipeline output to review.
            layer: Current pipeline layer (1, 2, 3).
            iteration: Current review iteration number.
            prior_reviews: Reviews from predecessor agents in the DAG (optional).
        """
        pass

    def debate_response(self, story_draft, layer, own_review, all_reviews, round2_entries=None):
        """React to other agents' reviews. Default: no challenges.

        P0-6: round2_entries lets Round 3 see Round 2 challenges (rebuttal context).
        """
        return []

    @staticmethod
    def _format_round2_rebuttal_context(round2_entries, target_agent_name: str) -> str:
        """Filter round2 entries that targeted this agent and return a rebuttal block."""
        if not round2_entries:
            return ""
        challenges_against_me = []
        for e in round2_entries:
            try:
                if getattr(e, "target_agent", "") == target_agent_name and \
                   str(getattr(e, "stance", "")).lower().endswith("challenge"):
                    challenges_against_me.append(
                        f"- [{getattr(e, 'agent_name', '?')}] {getattr(e, 'reasoning', '')[:200]}"
                    )
            except Exception:
                continue
        if not challenges_against_me:
            return ""
        return "## Round 2 challenges against you (rebut directly):\n" + "\n".join(challenges_against_me[:6])

    def _parse_debate_llm_response(self, result: dict, all_reviews: list[AgentReview]) -> list[DebateEntry]:
        """Parse LLM debate JSON into list[DebateEntry]. Validates targets, clamps scores."""
        entries_raw = result.get("entries", [])
        if not isinstance(entries_raw, list):
            return []
        valid_agents = {r.agent_name for r in all_reviews}
        entries = []
        for raw in entries_raw:
            stance_str = str(raw.get("stance", "neutral")).lower()
            if stance_str not in ("challenge", "support", "neutral"):
                stance_str = "neutral"
            target = raw.get("target_agent", "")
            if target and target not in valid_agents:
                continue  # skip hallucinated agent names
            revised = raw.get("revised_score")
            if revised is not None:
                try:
                    revised = max(0.0, min(1.0, float(revised)))
                except (TypeError, ValueError):
                    revised = None
            target_issue = str(raw.get("target_issue", ""))
            if len(target_issue) > 100:
                logger.debug("target_issue truncated from %d to 100 chars", len(target_issue))
                target_issue = target_issue[:100]
            entries.append(DebateEntry(
                agent_name=self.name,
                round_number=2,
                stance=DebateStance(stance_str),
                target_agent=target,
                target_issue=target_issue,
                reasoning=str(raw.get("reasoning", "")),
                revised_score=revised,
            ))
        return entries

    def _get_chapter_excerpt(self, story_draft, max_chars=1500):
        """Extract chapter text from PipelineOutput or StoryDraft."""
        chapters = None
        if hasattr(story_draft, 'enhanced_story') and story_draft.enhanced_story:
            chapters = story_draft.enhanced_story.chapters
        elif hasattr(story_draft, 'story_draft') and story_draft.story_draft:
            chapters = story_draft.story_draft.chapters
        elif hasattr(story_draft, 'chapters'):
            chapters = story_draft.chapters
        if not chapters:
            return "Không có nội dung."
        return "\n".join(c.content[:500] for c in chapters[:3])[:max_chars]

    def _parse_review_json(self, result: dict, layer: int, iteration: int) -> AgentReview:
        """Parse JSON response thành AgentReview."""
        score = result.get("score", 0.5)
        return AgentReview(
            agent_role=self.role,
            agent_name=self.name,
            score=score,
            issues=result.get("issues", []),
            suggestions=result.get("suggestions", []),
            approved=score >= 0.6,
            refined_content=result.get("refined_content"),
            layer=layer,
            iteration=iteration,
        )
