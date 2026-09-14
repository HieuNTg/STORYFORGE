"""Integration check for TEST_PLAN §3.1 — the craft lane runs end to end.

The unit tests in `test_agent_lane_config.py` drive a mocked panel, which proves
the config field exists but not that the eight real agents, the DAG tiers and the
debate actually execute. This drives the real `AgentRegistry`, the real agent
classes and the real `DebateOrchestrator`, mocking only at the LLM boundary
(`LLMClient`) so no provider is called and no tokens are spent.

Before the `debate_mode` fix this whole path raised AttributeError on the default
configuration and every review was discarded.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from config.defaults import LLMConfig, PipelineConfig
from models.schemas import Chapter, EnhancedStory, PipelineOutput, StoryDraft


class _RealConfig:
    """ConfigManager stand-in backed by the real dataclasses."""

    def __init__(self):
        self.pipeline = PipelineConfig()
        self.llm = LLMConfig()
        self.llm.max_parallel_workers = 1

    def load(self):
        return self


def _review_json(score=0.82):
    return {
        "score": score,
        "issues": ["nhịp chương 2 hơi chậm"],
        "suggestions": ["siết lại đoạn mở đầu chương 2"],
        "approved": True,
    }


def _fake_llm():
    """An LLMClient whose every call returns a plausible review payload."""
    llm = MagicMock()
    llm.generate_json.return_value = _review_json()
    llm.generate.return_value = json.dumps(_review_json())
    llm.generate_for_layer.return_value = json.dumps(_review_json())
    return llm


def _story_output() -> PipelineOutput:
    chapters = [
        Chapter(
            chapter_number=i,
            title=f"Chương {i}",
            content=f"Lan và Minh đối mặt nhau lần thứ {i}. " * 40,
            word_count=200,
            summary=f"tóm tắt chương {i}",
        )
        for i in (1, 2)
    ]
    draft = StoryDraft(
        title="Bóng tối Hà Nội",
        genre="hiện đại",
        chapters=chapters,
    )
    return PipelineOutput(
        story_draft=draft,
        enhanced_story=EnhancedStory(
            title=draft.title, genre=draft.genre, chapters=chapters, drama_score=0.7
        ),
    )


@pytest.fixture
def registry_with_real_agents():
    from pipeline.agents.agent_registry import AgentRegistry

    AgentRegistry._instance = None
    with patch("pipeline.agents.base_agent.LLMClient", return_value=_fake_llm()):
        from pipeline.agents import register_all_agents
        import pipeline.agents as agents_pkg

        # register_all_agents guards on a module global; reset so agents are
        # constructed here, with the patched LLM client.
        agents_pkg._agents_registered = False
        register_all_agents()
        yield AgentRegistry()
    AgentRegistry._instance = None


class TestCraftLaneEndToEnd:
    def test_layer2_panel_produces_reviews_on_the_default_config(
        self, registry_with_real_agents
    ):
        registry = registry_with_real_agents
        agents = registry.get_agents_for_layer(2)
        assert agents, "no agents registered for layer 2"

        with patch(
            "pipeline.agents.agent_registry.ConfigManager", new=_RealConfig
        ), patch("pipeline.agents.base_agent.LLMClient", return_value=_fake_llm()):
            reviews = registry.run_review_cycle(
                _story_output(), layer=2, max_iterations=1
            )

        assert reviews, "the craft lane produced no reviews"

    def test_every_registered_layer2_agent_is_exercised(
        self, registry_with_real_agents
    ):
        """Guards against a partial panel that still returns 'some' reviews."""
        registry = registry_with_real_agents
        expected_roles = {a.role for a in registry.get_agents_for_layer(2)}

        with patch(
            "pipeline.agents.agent_registry.ConfigManager", new=_RealConfig
        ), patch("pipeline.agents.base_agent.LLMClient", return_value=_fake_llm()):
            reviews = registry.run_review_cycle(
                _story_output(), layer=2, max_iterations=1
            )

        seen_roles = {r.agent_role for r in reviews}
        assert seen_roles, "no agent roles came back"
        missing = expected_roles - seen_roles
        assert not missing, f"agents registered but never heard from: {missing}"

    def test_the_panel_is_not_a_single_agent(self, registry_with_real_agents):
        """The product claims a panel; one agent answering is not a panel."""
        registry = registry_with_real_agents
        assert len(registry.get_agents_for_layer(2)) >= 5


class TestNoSilentAttributeErrors:
    def test_review_cycle_does_not_swallow_a_code_defect(
        self, registry_with_real_agents
    ):
        """The original failure mode: AttributeError logged as a warning."""
        registry = registry_with_real_agents

        with patch(
            "pipeline.agents.agent_registry.ConfigManager", new=_RealConfig
        ), patch("pipeline.agents.base_agent.LLMClient", return_value=_fake_llm()):
            # Must not raise, and must not come back empty.
            reviews = registry.run_review_cycle(
                _story_output(), layer=2, max_iterations=1
            )

        assert len(reviews) > 0
