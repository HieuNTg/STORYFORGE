"""Regression tests: the layer-2 craft lane must survive a real config.

Every other agent-registry test patches ConfigManager with a MagicMock, and a
MagicMock answers to any attribute. That is precisely how `cfg.debate_mode`
survived in `agent_registry` while the field did not exist on PipelineConfig:
the default path raised AttributeError, `orchestrator_layers` swallowed it into
one warning line, and the whole craft-critique lane — 8 agents plus debate —
produced nothing for every default run.

These tests therefore drive the registry with the real dataclasses.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from config.defaults import LLMConfig, PipelineConfig
from pipeline.agents.agent_registry import AgentRegistry
from pipeline.agents.base_agent import BaseAgent


class _RealConfig:
    """ConfigManager stand-in backed by the real dataclasses, not a MagicMock."""

    def __init__(self):
        self.pipeline = PipelineConfig()
        self.llm = LLMConfig()
        self.llm.max_parallel_workers = 1


def _layer2_agent(name="MockDramaAgent", role="drama_critic"):
    review = MagicMock()
    review.approved = True
    review.score = 0.9
    review.issues = []
    review.suggestions = []
    review.agent_role = role
    review.agent_name = name

    agent = MagicMock(spec=BaseAgent)
    agent.name = name
    agent.role = role
    agent.layers = [2]
    agent.review.return_value = review
    return agent


class TestDebateModeConfig:
    def setup_method(self):
        AgentRegistry._instance = None

    def test_pipeline_config_exposes_debate_mode(self):
        """agent_registry reads cfg.debate_mode on every layer-2 cycle."""
        cfg = PipelineConfig()
        assert hasattr(cfg, "debate_mode")
        assert cfg.debate_mode in ("full", "lite")

    def test_debate_is_enabled_by_default(self):
        """Guards the premise: the broken read sat behind this default."""
        assert PipelineConfig().enable_agent_debate is True

    @patch("pipeline.agents.debate_orchestrator.DebateOrchestrator")
    @patch("pipeline.agents.agent_registry.ConfigManager", new=_RealConfig)
    def test_layer2_review_cycle_survives_real_config(self, mock_debate):
        """The default path must return reviews, not lose them to AttributeError."""
        # A real debate returns the round-1 reviews, merged with rebuttals.
        mock_debate.return_value.run_debate.side_effect = (
            lambda agents, output, layer, round1, callback=None: SimpleNamespace(
                final_reviews=round1
            )
        )

        registry = AgentRegistry()
        agent = _layer2_agent()
        registry.register(agent)

        reviews = registry.run_review_cycle(MagicMock(), layer=2, max_iterations=1)

        assert agent.review.called, "the panel never ran"
        assert reviews, "layer-2 reviews were discarded"

    @patch("pipeline.agents.debate_orchestrator.DebateOrchestrator")
    @patch("pipeline.agents.agent_registry.ConfigManager", new=_RealConfig)
    def test_debate_receives_the_configured_mode(self, mock_debate):
        """The value reaching DebateOrchestrator must be the config's, not a mock."""
        # A real debate returns the round-1 reviews, merged with rebuttals.
        mock_debate.return_value.run_debate.side_effect = (
            lambda agents, output, layer, round1, callback=None: SimpleNamespace(
                final_reviews=round1
            )
        )

        registry = AgentRegistry()
        registry.register(_layer2_agent())
        registry.run_review_cycle(MagicMock(), layer=2, max_iterations=1)

        assert mock_debate.called, "debate never ran on the default path"
        assert mock_debate.call_args.kwargs["debate_mode"] == "full"
        assert mock_debate.call_args.kwargs["max_rounds"] == PipelineConfig().max_debate_rounds


class TestAgentPanelFailureReporting:
    """A code defect in the panel must not read like a routine provider warning."""

    def test_programming_errors_are_reported_as_errors(self):
        from pipeline.orchestrator_layers import _report_agent_panel_failure

        lines = []
        _report_agent_panel_failure(2, AttributeError("debate_mode"), lines.append)
        assert lines and "[AGENTS] ERROR" in lines[0]

    def test_runtime_errors_stay_warnings(self):
        from pipeline.orchestrator_layers import _report_agent_panel_failure

        lines = []
        _report_agent_panel_failure(2, RuntimeError("provider 503"), lines.append)
        assert lines and "[AGENTS] WARN" in lines[0]
