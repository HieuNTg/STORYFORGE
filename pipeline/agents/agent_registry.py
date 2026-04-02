"""Registry quản lý và điều phối các agent."""
import asyncio
import importlib
import logging
import pkgutil
from typing import Callable, Optional
from config import ConfigManager
from models.schemas import AgentReview, PipelineOutput
from pipeline.agents.base_agent import BaseAgent
from pipeline.agents.agent_graph import AgentDAG

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
        """Đăng ký agent vào registry (skip duplicates by name)."""
        if any(a.name == agent.name for a in self._agents):
            return
        self._agents.append(agent)
        logger.info(f"Đã đăng ký agent: {agent.name} ({agent.role})")

    def auto_discover(self):
        """Auto-discover and register all BaseAgent subclasses in pipeline/agents/."""
        import pipeline.agents as agents_pkg

        skip = {"base_agent", "agent_registry", "agent_prompts", "agent_graph", "__init__"}
        editor_agent = None

        for _importer, modname, _ispkg in pkgutil.iter_modules(agents_pkg.__path__):
            if modname in skip:
                continue
            module = importlib.import_module(f"pipeline.agents.{modname}")
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BaseAgent)
                    and attr is not BaseAgent
                ):
                    instance = attr()
                    if instance.role == "editor_in_chief":
                        editor_agent = instance
                    else:
                        self.register(instance)

        # Editor always last — it aggregates all other agents
        if editor_agent:
            self.register(editor_agent)

    def get_agents_for_layer(self, layer: int) -> list[BaseAgent]:
        """Lấy danh sách agent hoạt động ở layer cụ thể."""
        return [a for a in self._agents if layer in a.layers]

    def _run_tier_parallel(
        self,
        tier_agents: list[BaseAgent],
        output: PipelineOutput,
        layer: int,
        iteration: int,
        prior_reviews: list[AgentReview],
        progress_callback: Optional[Callable[[str], None]],
    ) -> list[AgentReview]:
        """Run a single tier of agents in parallel; return their reviews.

        Uses asyncio.gather + run_in_executor so LLM calls are dispatched
        concurrently without tying up OS threads beyond the default thread pool.
        agent.review() is synchronous (wraps blocking LLM SDK); run_in_executor
        offloads each call so the event loop remains responsive between dispatches.
        """
        async def _gather_reviews() -> list[AgentReview]:
            loop = asyncio.get_running_loop()
            prior = prior_reviews if prior_reviews else None

            async def _one(agent: BaseAgent) -> AgentReview | None:
                try:
                    review: AgentReview = await loop.run_in_executor(
                        None, agent.review, output, layer, iteration, prior
                    )
                    if progress_callback:
                        status = "OK" if review.approved else "WARN"
                        progress_callback(
                            f"[AGENTS] {status} {agent.name}: {review.score:.1f}/1.0 "
                            f"({len(review.issues)} vấn đề)"
                        )
                    return review
                except Exception as e:
                    logger.warning(f"Agent {agent.name} lỗi ở iteration {iteration}: {e}")
                    return None

            gathered = await asyncio.gather(*[_one(a) for a in tier_agents])
            return [r for r in gathered if r is not None]

        return asyncio.run(_gather_reviews())

    def run_review_cycle(
        self,
        output: PipelineOutput,
        layer: int,
        max_iterations: int = 3,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> list[AgentReview]:
        """Chạy vòng đánh giá cho một layer.

        Uses DAG-ordered tiered execution when agent dependencies are declared.
        Falls back to flat-parallel (original behavior) if DAG validation fails
        or all agents have no dependencies.

        Returns: Danh sách tất cả reviews từ tất cả iterations.
        """
        agents = self.get_agents_for_layer(layer)
        if not agents:
            return []

        # Build DAG and determine execution tiers
        use_tiered = False
        tiers_of_agents: list[list[BaseAgent]] = []

        try:
            dag = AgentDAG()
            dag.build_from_registry(agents)
            dag.validate()
            tiers_of_agents = dag.get_agents_by_tier()
            # Only use tiered execution if there is more than one tier
            use_tiered = len(tiers_of_agents) > 1
        except ValueError as exc:
            logger.warning(
                "[AGENTS] DAG cycle detected — falling back to flat-parallel: %s", exc
            )
            use_tiered = False
        except Exception as exc:
            logger.warning(
                "[AGENTS] DAG build failed — falling back to flat-parallel: %s", exc
            )
            use_tiered = False

        all_reviews: list[AgentReview] = []

        for iteration in range(1, max_iterations + 1):
            if progress_callback:
                progress_callback(
                    f"[AGENTS] Vòng đánh giá {iteration}/{max_iterations} - Layer {layer}"
                )

            round_reviews: list[AgentReview] = []

            if use_tiered:
                # Tiered execution: sequential across tiers, parallel within each tier
                accumulated: list[AgentReview] = []
                for tier_idx, tier_agents in enumerate(tiers_of_agents):
                    if progress_callback and len(tiers_of_agents) > 1:
                        progress_callback(
                            f"[AGENTS] Tier {tier_idx + 1}/{len(tiers_of_agents)}: "
                            f"{[a.name for a in tier_agents]}"
                        )
                    tier_reviews = self._run_tier_parallel(
                        tier_agents, output, layer, iteration, accumulated, progress_callback
                    )
                    accumulated.extend(tier_reviews)
                    round_reviews.extend(tier_reviews)
            else:
                # Flat-parallel fallback (original behavior)
                round_reviews = self._run_tier_parallel(
                    agents, output, layer, iteration, [], progress_callback
                )

            # Multi-agent debate: run after round 1 reviews on layer 2
            if ConfigManager().pipeline.enable_agent_debate and layer == 2:
                from pipeline.agents.debate_orchestrator import DebateOrchestrator
                cfg = ConfigManager().pipeline
                orchestrator = DebateOrchestrator(
                    max_rounds=cfg.max_debate_rounds,
                    debate_mode=cfg.debate_mode,
                )
                debate_result = orchestrator.run_debate(
                    agents, output, layer, round_reviews, progress_callback
                )
                round_reviews = debate_result.final_reviews

            all_reviews.extend(round_reviews)

            # Kiểm tra tất cả đã approve chưa
            if all(r.approved for r in round_reviews):
                if progress_callback:
                    progress_callback(f"[AGENTS] Layer {layer} được duyệt!")
                break

            # Nếu chưa approve và còn iteration, tiếp tục
            if iteration < max_iterations and progress_callback:
                progress_callback("[AGENTS] Cần chỉnh sửa, vòng tiếp theo...")

        return all_reviews
