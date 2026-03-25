"""Base class cho tất cả agent trong phòng ban."""
from abc import ABC, abstractmethod
import logging
from typing import Optional
from models.schemas import AgentReview, PipelineOutput
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

    def debate_response(self, story_draft, layer, own_review, all_reviews):
        """React to other agents' reviews. Default: no challenges."""
        return []

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
