"""Sprint 2 — send low-stakes calls to the cheap model, and cap tiny replies.

The whole simulator ran on the premium tier: roughly 100 calls a run. Two of
those never reach the reader in any real sense — drama evaluation, consumed as a
single score, and reaction posts, which only ever appear truncated as
recent-posts filler. Agent turns and escalation events stay on the primary model
because they *are* the dramatic content.

The 8-agent craft panel returns a small `{score, issues[], suggestions[]}`
object and had no output cap at all. Its tier is configurable but stays on the
primary model by default: SmartRevisionService rewrites chapters from this
critique, so its judgement quality reaches the reader.
"""

from unittest.mock import MagicMock, patch

from config.defaults import PipelineConfig
from models.schemas import Character, Relationship
from pipeline.layer2_enhance.simulator import DramaSimulator


class _Cfg:
    def __init__(self, **over):
        self.pipeline = PipelineConfig()
        for k, v in over.items():
            setattr(self.pipeline, k, v)

    def load(self):
        return self


def _simulator():
    with patch("pipeline.layer2_enhance.simulator.LLMClient"):
        sim = DramaSimulator()
    sim.llm = MagicMock()
    sim.llm.generate_json.return_value = {"overall_drama_score": 0.7, "events": []}
    sim.relationships = [
        Relationship(character_a="Lan", character_b="Minh", relation_type="đối_thủ")
    ]
    sim.characters = [
        Character(name="Lan", role="protagonist", personality="quyết đoán")
    ]
    return sim


class TestSimulatorTierDefaults:
    def test_low_stakes_calls_default_to_cheap(self):
        sim = _simulator()
        with patch("config.ConfigManager", new=_Cfg):
            assert sim._low_stakes_tier() == "cheap"

    def test_the_flag_puts_them_back_on_the_primary_model(self):
        sim = _simulator()
        with patch(
            "config.ConfigManager", new=lambda: _Cfg(l2_cheap_low_stakes_calls=False)
        ):
            assert sim._low_stakes_tier() == "default"

    def test_config_is_the_only_source(self):
        """A missing config must not silently downgrade the model."""
        sim = _simulator()
        with patch("config.ConfigManager", side_effect=RuntimeError("no config")):
            assert sim._low_stakes_tier() == "default"

    def test_drama_evaluation_uses_the_low_stakes_tier(self):
        sim = _simulator()
        with patch("config.ConfigManager", new=_Cfg):
            sim.evaluate_drama([])
        assert sim.llm.generate_json.call_args.kwargs["model_tier"] == "cheap"


class TestAgentPanelCaps:
    def _agent(self):
        from pipeline.agents.drama_critic import DramaCriticAgent

        with patch("pipeline.agents.base_agent.LLMClient"):
            return DramaCriticAgent()

    def test_review_replies_are_capped(self):
        agent = self._agent()
        with patch("config.ConfigManager", new=_Cfg):
            assert agent.review_max_tokens == 1200

    def test_the_cap_is_configurable(self):
        agent = self._agent()
        with patch(
            "config.ConfigManager",
            new=lambda: _Cfg(l2_agent_review_max_tokens=400),
        ):
            assert agent.review_max_tokens == 400

    def test_panel_stays_on_the_primary_model_by_default(self):
        """Its critique drives rewrites, so downgrading is an explicit choice."""
        agent = self._agent()
        with patch("config.ConfigManager", new=_Cfg):
            assert agent.review_model_tier == "default"

    def test_panel_can_be_moved_to_cheap_by_config(self):
        agent = self._agent()
        with patch(
            "config.ConfigManager", new=lambda: _Cfg(l2_cheap_agent_panel=True)
        ):
            assert agent.review_model_tier == "cheap"

    def test_a_review_call_passes_both(self):
        agent = self._agent()
        agent.llm = MagicMock()
        agent.llm.generate_json.return_value = {
            "score": 0.8,
            "issues": [],
            "suggestions": [],
        }
        output = MagicMock()
        output.enhanced_story.chapters = []
        output.story_draft.chapters = []
        output.simulation_result = None

        with patch("config.ConfigManager", new=_Cfg):
            agent.review(output, layer=2, iteration=1)

        kwargs = agent.llm.generate_json.call_args.kwargs
        assert kwargs["max_tokens"] == 1200
        assert kwargs["model_tier"] == "default"


class TestEveryPanelCallIsCapped:
    def test_no_uncapped_review_call_remains(self):
        """Source guard: an unbounded reply is billed against the full budget."""
        import glob
        import re

        offenders = []
        for path in glob.glob("pipeline/agents/*.py"):
            src = open(path, encoding="utf-8").read()
            for match in re.finditer(r"generate_json\((.*?)\n        \)", src, re.S):
                call = match.group(1)
                if "max_tokens" not in call:
                    offenders.append(path)
        assert not offenders, f"uncapped panel calls in: {sorted(set(offenders))}"
