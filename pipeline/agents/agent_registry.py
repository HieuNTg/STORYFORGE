"""Registry quản lý và điều phối các agent."""
import logging
from typing import Callable, Optional
from models.schemas import AgentReview, PipelineOutput
from pipeline.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Singleton registry cho tất cả agent trong phòng ban."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._agents = []
        return cls._instance

    def register(self, agent: BaseAgent):
        """Đăng ký agent vào registry."""
        self._agents.append(agent)
        logger.info(f"Đã đăng ký agent: {agent.name} ({agent.role})")

    def get_agents_for_layer(self, layer: int) -> list[BaseAgent]:
        """Lấy danh sách agent hoạt động ở layer cụ thể."""
        return [a for a in self._agents if layer in a.layers]

    def run_review_cycle(
        self,
        output: PipelineOutput,
        layer: int,
        max_iterations: int = 3,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> list[AgentReview]:
        """Chạy vòng đánh giá cho một layer.

        Returns: Danh sách tất cả reviews từ tất cả iterations.
        """
        agents = self.get_agents_for_layer(layer)
        if not agents:
            return []

        all_reviews: list[AgentReview] = []

        for iteration in range(1, max_iterations + 1):
            if progress_callback:
                progress_callback(
                    f"[AGENTS] Vòng đánh giá {iteration}/{max_iterations} - Layer {layer}"
                )

            round_reviews: list[AgentReview] = []
            for agent in agents:
                try:
                    if progress_callback:
                        progress_callback(f"[AGENTS] {agent.name} đang đánh giá...")
                    review = agent.review(output, layer, iteration)
                    round_reviews.append(review)
                    all_reviews.append(review)

                    if progress_callback:
                        status = "OK" if review.approved else "WARN"
                        progress_callback(
                            f"[AGENTS] {status} {agent.name}: {review.score:.1f}/1.0 "
                            f"({len(review.issues)} vấn đề)"
                        )
                except Exception as e:
                    logger.warning(f"Agent {agent.name} lỗi ở iteration {iteration}: {e}")

            # Kiểm tra tất cả đã approve chưa
            if all(r.approved for r in round_reviews):
                if progress_callback:
                    progress_callback(f"[AGENTS] Layer {layer} được duyệt!")
                break

            # Nếu chưa approve và còn iteration, tiếp tục
            if iteration < max_iterations and progress_callback:
                progress_callback("[AGENTS] Cần chỉnh sửa, vòng tiếp theo...")

        return all_reviews
