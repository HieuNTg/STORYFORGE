"""Comprehensive tests for 0%-coverage pipeline and agent modules.

Targets:
  - pipeline/agents/debate_orchestrator.py
  - pipeline/agents/agent_registry.py
  - pipeline/layer1_story/batch_generator.py
  - services/seedream_client.py
  - services/replicate_ip_adapter.py
"""

import os
import tempfile
import base64
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Shared schema helpers
# ---------------------------------------------------------------------------
from models.schemas import (
    AgentReview,
    DebateEntry,
    DebateResult,
    DebateStance,
    Chapter,
    StoryDraft,
    StoryContext,
    ChapterOutline,
    PipelineOutput,
)


def _make_review(
    agent_name: str = "agent_a", score: float = 0.8, approved: bool = True
) -> AgentReview:
    return AgentReview(
        agent_role="critic",
        agent_name=agent_name,
        score=score,
        issues=[],
        suggestions=[],
        approved=approved,
    )


def _make_debate_entry(
    agent_name: str = "agent_a",
    target_agent: str = "agent_b",
    stance: DebateStance = DebateStance.CHALLENGE,
    revised_score: Optional[float] = 0.5,
    reasoning: str = "some reason",
    round_number: int = 2,
) -> DebateEntry:
    return DebateEntry(
        agent_name=agent_name,
        target_agent=target_agent,
        stance=stance,
        revised_score=revised_score,
        reasoning=reasoning,
        round_number=round_number,
    )


# ===========================================================================
# debate_orchestrator.py
# ===========================================================================


class TestDebateOrchestratorModule:
    """Tests for _find_review, _merge_debate_into_reviews, _estimate helpers."""

    def test_find_review_found(self):
        from pipeline.agents.debate_orchestrator import _find_review

        reviews = [_make_review("agent_a"), _make_review("agent_b")]
        assert _find_review(reviews, "agent_a").agent_name == "agent_a"

    def test_find_review_not_found(self):
        from pipeline.agents.debate_orchestrator import _find_review

        reviews = [_make_review("agent_a")]
        assert _find_review(reviews, "agent_z") is None

    def test_find_review_empty_list(self):
        from pipeline.agents.debate_orchestrator import _find_review

        assert _find_review([], "x") is None

    def test_merge_no_entries(self):
        from pipeline.agents.debate_orchestrator import _merge_debate_into_reviews

        reviews = [_make_review("agent_a", score=0.8)]
        result = _merge_debate_into_reviews(reviews, [])
        assert len(result) == 1
        assert result[0].score == pytest.approx(0.8)

    def test_merge_revised_score_averaged(self):
        from pipeline.agents.debate_orchestrator import _merge_debate_into_reviews

        reviews = [_make_review("agent_a", score=0.8)]
        entry = _make_debate_entry("agent_b", "agent_a", revised_score=0.4)
        result = _merge_debate_into_reviews(reviews, [entry])
        assert result[0].score == pytest.approx((0.8 + 0.4) / 2)

    def test_merge_reasoning_appended(self):
        from pipeline.agents.debate_orchestrator import _merge_debate_into_reviews

        reviews = [_make_review("agent_a")]
        entry = _make_debate_entry("challenger", "agent_a", reasoning="bad writing")
        result = _merge_debate_into_reviews(reviews, [entry])
        assert any("bad writing" in s for s in result[0].suggestions)

    def test_merge_unknown_target_ignored(self):
        from pipeline.agents.debate_orchestrator import _merge_debate_into_reviews

        reviews = [_make_review("agent_a")]
        entry = _make_debate_entry("agent_x", "agent_nonexistent", revised_score=0.1)
        result = _merge_debate_into_reviews(reviews, [entry])
        # Original score should be unchanged
        assert result[0].score == pytest.approx(0.8)

    def test_merge_no_revised_score(self):
        from pipeline.agents.debate_orchestrator import _merge_debate_into_reviews

        reviews = [_make_review("agent_a", score=0.7)]
        entry = _make_debate_entry(
            "agent_b", "agent_a", revised_score=None, reasoning="ok"
        )
        result = _merge_debate_into_reviews(reviews, [entry])
        assert result[0].score == pytest.approx(0.7)

    def test_estimate_agent_tokens_default(self):
        from pipeline.agents.debate_orchestrator import _estimate_agent_tokens

        agent = MagicMock(spec=[])
        assert _estimate_agent_tokens(agent) == 300

    def test_estimate_agent_tokens_with_usage(self):
        from pipeline.agents.debate_orchestrator import _estimate_agent_tokens

        agent = MagicMock()
        agent._last_token_usage = {"total_tokens": 500}
        assert _estimate_agent_tokens(agent) == 500

    def test_estimate_agent_tokens_bad_usage(self):
        from pipeline.agents.debate_orchestrator import _estimate_agent_tokens

        agent = MagicMock()
        agent._last_token_usage = "garbage"
        # Should fall back to default
        assert _estimate_agent_tokens(agent) == 300

    def test_estimate_agent_cost_no_tracker(self):
        from pipeline.agents.debate_orchestrator import _estimate_agent_cost

        with patch(
            "pipeline.agents.debate_orchestrator._get_agent_model",
            side_effect=Exception("no"),
        ):
            cost = _estimate_agent_cost(300, MagicMock())
        assert cost == 0.0

    def test_get_agent_model_fallback(self):
        from pipeline.agents.debate_orchestrator import _get_agent_model

        # ConfigManager is imported lazily inside the function, so patch via config module
        with patch("config.ConfigManager", side_effect=Exception("no cfg")):
            result = _get_agent_model(MagicMock())
        assert result == "unknown"

    def test_get_agent_model_success(self):
        from pipeline.agents.debate_orchestrator import _get_agent_model

        mock_cfg = MagicMock()
        mock_cfg.return_value.llm.model = "gpt-4"
        with patch("config.ConfigManager", mock_cfg):
            result = _get_agent_model(MagicMock())
        assert result == "gpt-4"


class TestDebateOrchestrator:
    """Tests for DebateOrchestrator.run_debate()."""

    def _make_orchestrator(self, **kwargs):
        from pipeline.agents.debate_orchestrator import DebateOrchestrator

        return DebateOrchestrator(**kwargs)

    def _make_agent(self, name: str, role: str = "critic", review_entry=None):
        agent = MagicMock()
        agent.name = name
        agent.role = role
        if review_entry is None:
            review_entry = []
        agent.debate_response.return_value = review_entry
        return agent

    # -- lite mode --

    def test_lite_mode_no_matching_agents_skips(self):
        orch = self._make_orchestrator(debate_mode="lite")
        agents = [self._make_agent("agent_x", role="unknown_role")]
        reviews = [_make_review("agent_x")]
        result = orch.run_debate(agents, {}, 2, reviews)
        assert result.debate_skipped is True
        assert result.final_reviews == reviews

    def test_lite_mode_uses_only_lite_agents(self):
        orch = self._make_orchestrator(debate_mode="lite")
        editor = self._make_agent("the_editor", role="editor_in_chief")
        non_lite = self._make_agent("some_agent", role="other_role")
        reviews = [_make_review("the_editor")]
        # No challenges from editor (returns empty)
        editor.debate_response.return_value = []
        orch.run_debate([editor, non_lite], {}, 2, reviews)
        # non_lite should not be called
        non_lite.debate_response.assert_not_called()

    def test_lite_mode_with_challenge_skips_round3(self):
        orch = self._make_orchestrator(debate_mode="lite")
        agent = self._make_agent("drama_critic", role="drama_critic")
        reviews = [_make_review("drama_critic", score=0.7)]
        challenge = _make_debate_entry(
            "drama_critic", "drama_critic", stance=DebateStance.CHALLENGE
        )
        agent.debate_response.return_value = [challenge]
        result = orch.run_debate([agent], {}, 2, reviews)
        assert result.debate_skipped is False
        assert result.total_challenges == 1
        # round3 should not exist (lite mode)
        assert len(result.rounds) == 2

    def test_progress_callback_called_lite(self):
        orch = self._make_orchestrator(debate_mode="lite")
        agent = self._make_agent("editor_in_chief", role="editor_in_chief")
        reviews = [_make_review("editor_in_chief")]
        agent.debate_response.return_value = []
        calls = []
        orch.run_debate([agent], {}, 2, reviews, progress_callback=calls.append)
        assert any("DEBATE-LITE" in c for c in calls)

    # -- full mode --

    def test_full_mode_no_challenges_skips_round3(self):
        orch = self._make_orchestrator(debate_mode="full")
        agent = self._make_agent("agent_a")
        reviews = [_make_review("agent_a")]
        agent.debate_response.return_value = []  # no challenges
        result = orch.run_debate([agent], {}, 2, reviews)
        assert result.debate_skipped is True
        assert result.total_challenges == 0

    def test_full_mode_with_challenges_runs_round3(self):
        orch = self._make_orchestrator(debate_mode="full")
        agent = self._make_agent("agent_a")
        reviews = [_make_review("agent_a", score=0.8)]
        challenge = _make_debate_entry(
            "agent_a", "agent_a", stance=DebateStance.CHALLENGE
        )
        # Round 2 returns challenge; Round 3 (rebuttal) returns neutral
        rebuttal = _make_debate_entry(
            "agent_a", "agent_a", stance=DebateStance.SUPPORT, round_number=3
        )
        agent.debate_response.side_effect = [[challenge], [rebuttal]]
        result = orch.run_debate([agent], {}, 2, reviews)
        assert result.debate_skipped is False
        assert result.total_challenges == 1

    def test_full_mode_progress_callback(self):
        orch = self._make_orchestrator(debate_mode="full")
        agent = self._make_agent("agent_a")
        reviews = [_make_review("agent_a", score=0.8)]
        challenge = _make_debate_entry(
            "agent_a", "agent_a", stance=DebateStance.CHALLENGE
        )
        rebuttal = _make_debate_entry("agent_a", "agent_a", stance=DebateStance.SUPPORT)
        agent.debate_response.side_effect = [[challenge], [rebuttal]]
        msgs = []
        orch.run_debate([agent], {}, 2, reviews, progress_callback=msgs.append)
        assert any("challenge" in m.lower() for m in msgs)

    def test_session_tokens_reset_each_run(self):
        orch = self._make_orchestrator(debate_mode="full")
        agent = self._make_agent("agent_a")
        reviews = [_make_review("agent_a")]
        agent.debate_response.return_value = []
        orch._session_tokens = 9999
        orch.run_debate([agent], {}, 2, reviews)
        # After run, they may have been set but starting fresh is what matters
        # Just verify the call completes and no stale state causes errors
        assert orch._session_tokens >= 0

    # -- budget helpers --

    def test_budget_exceeded_no_violations(self):
        orch = self._make_orchestrator()
        assert orch._budget_exceeded("Round 2") is False

    def test_budget_exceeded_tokens_warn(self):
        orch = self._make_orchestrator(budget_action="warn", max_total_tokens=100)
        orch._session_tokens = 200
        # warn mode: returns False (never skips)
        assert orch._budget_exceeded("Round 2") is False

    def test_budget_exceeded_tokens_skip(self):
        orch = self._make_orchestrator(budget_action="skip", max_total_tokens=100)
        orch._session_tokens = 200
        assert orch._budget_exceeded("Round 2") is True

    def test_budget_exceeded_cost_skip(self):
        orch = self._make_orchestrator(budget_action="skip", max_cost_usd=0.01)
        orch._session_cost_usd = 1.0
        assert orch._budget_exceeded("Round 2") is True

    def test_budget_exceeded_abort_raises(self):
        from pipeline.agents.debate_orchestrator import BudgetExceededError

        orch = self._make_orchestrator(budget_action="abort", max_total_tokens=100)
        orch._session_tokens = 500
        with pytest.raises(BudgetExceededError):
            orch._budget_exceeded("Round 2")

    def test_budget_exceeded_callback_called(self):
        orch = self._make_orchestrator(budget_action="skip", max_total_tokens=100)
        orch._session_tokens = 200
        msgs = []
        orch._budget_exceeded("Round 2", progress_callback=msgs.append)
        assert len(msgs) == 1

    def test_estimate_tokens(self):
        orch = self._make_orchestrator()
        text = "hello world!"  # 12 chars → 3 tokens
        assert orch._estimate_tokens(text) == 3

    def test_token_budget_per_round_exceeded_aborts_round2(self):
        from pipeline.agents.debate_orchestrator import BudgetExceededError

        orch = self._make_orchestrator(
            budget_action="abort",
            max_tokens_per_round=1,  # tiny — any non-empty prompt will exceed
        )
        agent = self._make_agent("agent_a")
        review = _make_review("agent_a")
        # Stuff suggestions so getattr(own_review, 'suggestions', '') contributes chars
        review.suggestions = ["x" * 200]
        reviews = [review]
        agent.debate_response.return_value = []
        with pytest.raises(BudgetExceededError):
            orch.run_debate([agent], {}, 2, reviews)

    def test_total_token_budget_exceeded_stops_round2(self):
        orch = self._make_orchestrator(
            debate_mode="full",
            max_total_tokens=0,  # already exhausted at start
        )
        orch._session_tokens = 1  # exceed immediately
        agent = self._make_agent("agent_a")
        reviews = [_make_review("agent_a")]
        agent.debate_response.return_value = []
        # Should proceed but skip when total budget hit mid-loop
        result = orch.run_debate([agent], {}, 2, reviews)
        assert result is not None

    def test_run_debate_with_budget_skip_before_round2(self):
        orch = self._make_orchestrator(budget_action="skip", max_total_tokens=0)
        orch._session_tokens = 100
        agent = self._make_agent("agent_a")
        reviews = [_make_review("agent_a")]
        result = orch.run_debate([agent], {}, 2, reviews)
        assert result.debate_skipped is True

    def test_run_debate_budget_skip_before_round3(self):
        orch = self._make_orchestrator(
            debate_mode="full", budget_action="skip", max_total_tokens=1000
        )
        agent = self._make_agent("agent_a")
        reviews = [_make_review("agent_a", score=0.8)]
        challenge = _make_debate_entry(
            "agent_a", "agent_a", stance=DebateStance.CHALLENGE
        )
        agent.debate_response.return_value = [challenge]
        # Artificially exhaust budget before round 3
        orch._session_tokens = 2000
        result = orch.run_debate([agent], {}, 2, reviews)
        # Should return result from round 2 data
        assert result is not None
        assert result.total_challenges >= 0

    def test_agent_without_review_skipped(self):
        orch = self._make_orchestrator(debate_mode="full")
        agent = self._make_agent("agent_no_review")
        reviews = [_make_review("other_agent")]  # no review for agent_no_review
        agent.debate_response.return_value = []
        orch.run_debate([agent], {}, 2, reviews)
        agent.debate_response.assert_not_called()

    def test_round3_budget_abort_raises(self):
        from pipeline.agents.debate_orchestrator import BudgetExceededError

        # Use a mid-range per-round limit: pass round2 (1 agent * ~300 tokens default),
        # but set session tokens high so _budget_exceeded returns abort before round3.
        orch = self._make_orchestrator(
            debate_mode="full",
            budget_action="abort",
            max_total_tokens=1,  # session total cap tiny → abort before round3
        )
        agent = self._make_agent("agent_a")
        review = _make_review("agent_a", score=0.8)
        challenge = _make_debate_entry(
            "agent_a", "agent_a", stance=DebateStance.CHALLENGE
        )
        agent.debate_response.return_value = [challenge]
        # After round2 agent call, _session_tokens will be 300 (default), exceeding max_total_tokens=1
        # _budget_exceeded("Round 3") with budget_action="abort" will raise
        with pytest.raises(BudgetExceededError):
            orch.run_debate([agent], {}, 2, [review])


# ===========================================================================
# agent_registry.py
# ===========================================================================


class TestAgentRegistry:
    """Tests for AgentRegistry singleton."""

    def setup_method(self):
        # Reset singleton between tests
        from pipeline.agents.agent_registry import AgentRegistry

        AgentRegistry._instance = None

    def _make_registry(self):
        from pipeline.agents.agent_registry import AgentRegistry

        return AgentRegistry()

    def _make_agent(
        self, name: str = "test_agent", role: str = "critic", layers: list = None
    ):
        agent = MagicMock()
        agent.name = name
        agent.role = role
        agent.layers = layers or [1, 2]
        return agent

    def test_singleton(self):
        r1 = self._make_registry()
        r2 = self._make_registry()
        assert r1 is r2

    def test_register_agent(self):
        reg = self._make_registry()
        agent = self._make_agent("agent_1")
        reg.register(agent)
        assert agent in reg._agents

    def test_register_duplicate_skipped(self):
        reg = self._make_registry()
        agent = self._make_agent("agent_1")
        reg.register(agent)
        reg.register(agent)
        assert len([a for a in reg._agents if a.name == "agent_1"]) == 1

    def test_get_agents_for_layer(self):
        reg = self._make_registry()
        a1 = self._make_agent("a1", layers=[1])
        a2 = self._make_agent("a2", layers=[2])
        a3 = self._make_agent("a3", layers=[1, 2])
        reg.register(a1)
        reg.register(a2)
        reg.register(a3)
        layer1 = reg.get_agents_for_layer(1)
        assert a1 in layer1
        assert a3 in layer1
        assert a2 not in layer1

    def test_get_agents_for_layer_empty(self):
        reg = self._make_registry()
        assert reg.get_agents_for_layer(99) == []

    def test_run_tier_parallel_returns_reviews(self):
        reg = self._make_registry()
        review = _make_review("agent_a")
        agent = self._make_agent("agent_a")
        agent.review.return_value = review
        output = PipelineOutput()
        results = reg._run_tier_parallel([agent], output, 1, 1, [], None)
        assert len(results) == 1
        assert results[0].agent_name == "agent_a"

    def test_run_tier_parallel_filters_none(self):
        reg = self._make_registry()
        agent = self._make_agent("bad_agent")
        agent.review.side_effect = Exception("LLM error")
        output = PipelineOutput()
        results = reg._run_tier_parallel([agent], output, 1, 1, [], None)
        assert results == []

    def test_run_tier_parallel_progress_callback(self):
        reg = self._make_registry()
        review = _make_review("agent_a")
        agent = self._make_agent("agent_a")
        agent.review.return_value = review
        output = PipelineOutput()
        msgs = []
        reg._run_tier_parallel([agent], output, 1, 1, [], msgs.append)
        assert len(msgs) > 0

    def test_run_review_cycle_no_agents(self):
        reg = self._make_registry()
        output = PipelineOutput()
        result = reg.run_review_cycle(output, layer=99)
        assert result == []

    def test_run_review_cycle_all_approved(self):
        reg = self._make_registry()
        agent = self._make_agent("agent_a", layers=[1])
        review = _make_review("agent_a", approved=True)
        agent.review.return_value = review
        reg.register(agent)
        output = PipelineOutput()

        with (
            patch("pipeline.agents.agent_registry.AgentDAG") as MockDAG,
            patch("pipeline.agents.agent_registry.ConfigManager") as MockCfg,
        ):
            MockCfg.return_value.pipeline.enable_agent_debate = False
            dag_instance = MockDAG.return_value
            dag_instance.get_agents_by_tier.return_value = [[agent]]
            dag_instance.validate.return_value = None
            # Single tier → use_tiered=False (len==1)
            result = reg.run_review_cycle(output, layer=1, max_iterations=3)

        assert len(result) >= 1

    def test_run_review_cycle_progress_callback(self):
        reg = self._make_registry()
        agent = self._make_agent("agent_a", layers=[1])
        review = _make_review("agent_a", approved=True)
        agent.review.return_value = review
        reg.register(agent)
        output = PipelineOutput()
        msgs = []

        with (
            patch("pipeline.agents.agent_registry.AgentDAG") as MockDAG,
            patch("pipeline.agents.agent_registry.ConfigManager") as MockCfg,
        ):
            MockCfg.return_value.pipeline.enable_agent_debate = False
            dag_instance = MockDAG.return_value
            dag_instance.get_agents_by_tier.return_value = [[agent]]
            reg.run_review_cycle(
                output, layer=1, max_iterations=1, progress_callback=msgs.append
            )

        assert len(msgs) > 0

    def test_run_review_cycle_dag_cycle_fallback(self):
        reg = self._make_registry()
        agent = self._make_agent("agent_a", layers=[1])
        review = _make_review("agent_a", approved=True)
        agent.review.return_value = review
        reg.register(agent)
        output = PipelineOutput()

        with (
            patch("pipeline.agents.agent_registry.AgentDAG") as MockDAG,
            patch("pipeline.agents.agent_registry.ConfigManager") as MockCfg,
        ):
            MockCfg.return_value.pipeline.enable_agent_debate = False
            MockDAG.return_value.validate.side_effect = ValueError("cycle!")
            result = reg.run_review_cycle(output, layer=1, max_iterations=1)

        assert isinstance(result, list)

    def test_run_review_cycle_dag_build_exception_fallback(self):
        reg = self._make_registry()
        agent = self._make_agent("agent_a", layers=[1])
        review = _make_review("agent_a", approved=True)
        agent.review.return_value = review
        reg.register(agent)
        output = PipelineOutput()

        with (
            patch(
                "pipeline.agents.agent_registry.AgentDAG",
                side_effect=Exception("build fail"),
            ),
            patch("pipeline.agents.agent_registry.ConfigManager") as MockCfg,
        ):
            MockCfg.return_value.pipeline.enable_agent_debate = False
            result = reg.run_review_cycle(output, layer=1, max_iterations=1)

        assert isinstance(result, list)

    def test_run_review_cycle_debate_triggered_on_layer2(self):
        reg = self._make_registry()
        agent = self._make_agent("agent_a", layers=[2])
        review = _make_review("agent_a", approved=True)
        agent.review.return_value = review
        reg.register(agent)
        output = PipelineOutput()

        mock_debate_result = DebateResult(
            rounds=[[], []],
            final_reviews=[review],
            debate_skipped=False,
            total_challenges=0,
        )

        with (
            patch("pipeline.agents.agent_registry.AgentDAG") as MockDAG,
            patch("pipeline.agents.agent_registry.ConfigManager") as MockCfg,
            patch("pipeline.agents.debate_orchestrator.DebateOrchestrator") as MockOrch,
        ):
            MockCfg.return_value.pipeline.enable_agent_debate = True
            MockCfg.return_value.pipeline.max_debate_rounds = 3
            MockCfg.return_value.pipeline.debate_mode = "full"
            dag_instance = MockDAG.return_value
            dag_instance.get_agents_by_tier.return_value = [[agent]]
            MockOrch.return_value.run_debate.return_value = mock_debate_result
            result = reg.run_review_cycle(output, layer=2, max_iterations=1)

        assert isinstance(result, list)

    def test_run_review_cycle_not_all_approved_continues(self):
        reg = self._make_registry()
        agent = self._make_agent("agent_a", layers=[1])
        not_approved = _make_review("agent_a", approved=False)
        approved = _make_review("agent_a", approved=True)
        agent.review.side_effect = [not_approved, approved]
        reg.register(agent)
        output = PipelineOutput()
        msgs = []

        with (
            patch("pipeline.agents.agent_registry.AgentDAG") as MockDAG,
            patch("pipeline.agents.agent_registry.ConfigManager") as MockCfg,
        ):
            MockCfg.return_value.pipeline.enable_agent_debate = False
            MockDAG.return_value.validate.side_effect = ValueError("cycle")
            result = reg.run_review_cycle(
                output, layer=1, max_iterations=2, progress_callback=msgs.append
            )

        assert len(result) == 2  # two iterations ran

    def test_auto_discover_does_not_crash(self):
        """auto_discover exercises import machinery; just verify no exception."""
        reg = self._make_registry()
        # May or may not find agents depending on env — should not raise
        try:
            reg.auto_discover()
        except Exception as exc:
            pytest.fail(f"auto_discover raised unexpectedly: {exc}")


# ===========================================================================
# batch_generator.py
# ===========================================================================


class TestFrozenContext:
    def test_frozen_context_copies_lists(self):
        from pipeline.layer1_story.batch_generator import FrozenContext

        ctx = StoryContext(total_chapters=5)
        ctx.recent_summaries = ["s1", "s2"]
        ctx.character_states = []
        ctx.plot_events = []
        fc = FrozenContext(ctx, ["ch1_text"])
        assert fc.recent_summaries == ["s1", "s2"]
        assert fc.chapter_texts == ["ch1_text"]
        # Mutation of original doesn't affect frozen
        ctx.recent_summaries.append("s3")
        assert "s3" not in fc.recent_summaries


class TestBatchChapterGenerator:
    def _make_generator(self, parallel=False, batch_size=3):
        from pipeline.layer1_story.batch_generator import BatchChapterGenerator

        gen = MagicMock()
        config = MagicMock()
        config.pipeline.chapter_batch_size = batch_size
        config.pipeline.parallel_chapters_enabled = parallel
        config.pipeline.context_window_chapters = 5
        config.pipeline.story_bible_enabled = False
        config.pipeline.enable_self_review = False
        gen.config = config
        gen.llm = MagicMock()
        gen._get_self_reviewer.return_value = None
        gen.token_budget_per_chapter = 2000
        gen.bible_manager = MagicMock()
        return BatchChapterGenerator(gen)

    def _make_outline(self, num: int) -> ChapterOutline:
        return ChapterOutline(
            chapter_number=num,
            title=f"Chapter {num}",
            summary="A summary",
        )

    def _make_chapter(self, num: int) -> Chapter:
        return Chapter(
            chapter_number=num, title=f"Chapter {num}", content="Content " * 50
        )

    def test_split_batches_basic(self):
        bg = self._make_generator(batch_size=2)
        outlines = [self._make_outline(i) for i in range(1, 6)]
        batches = bg._split_batches(outlines)
        assert len(batches) == 3
        assert len(batches[0]) == 2
        assert len(batches[-1]) == 1

    def test_split_batches_exact_multiple(self):
        bg = self._make_generator(batch_size=3)
        outlines = [self._make_outline(i) for i in range(1, 7)]
        batches = bg._split_batches(outlines)
        assert len(batches) == 2
        assert all(len(b) == 3 for b in batches)

    def test_build_sibling_context_single(self):
        from pipeline.layer1_story.batch_generator import BatchChapterGenerator

        outline = self._make_outline(1)
        result = BatchChapterGenerator._build_sibling_context([outline])
        assert result == ""

    def test_build_sibling_context_multiple(self):
        from pipeline.layer1_story.batch_generator import BatchChapterGenerator

        outlines = [self._make_outline(1), self._make_outline(2)]
        result = BatchChapterGenerator._build_sibling_context(outlines)
        assert "Ch1" in result
        assert "Ch2" in result

    def test_generate_chapters_sequential(self):
        bg = self._make_generator(parallel=False, batch_size=2)
        outlines = [self._make_outline(i) for i in range(1, 4)]
        draft = StoryDraft(title="T", genre="g")
        ctx = StoryContext(total_chapters=3)

        chapters = [self._make_chapter(i) for i in range(1, 4)]
        bg.gen._write_chapter_with_long_context.side_effect = chapters

        with patch(
            "pipeline.layer1_story.chapter_finalizer.process_chapter_post_write"
        ):
            result = bg.generate_chapters(
                draft, outlines, ctx, "Title", "fantasy", "style", [], None
            )
        assert len(result) == 3

    def test_generate_chapters_with_progress_callback(self):
        bg = self._make_generator(parallel=False, batch_size=5)
        outlines = [self._make_outline(1)]
        draft = StoryDraft(title="T", genre="g")
        ctx = StoryContext(total_chapters=1)
        bg.gen._write_chapter_with_long_context.return_value = self._make_chapter(1)
        msgs = []

        with patch(
            "pipeline.layer1_story.chapter_finalizer.process_chapter_post_write"
        ):
            bg.generate_chapters(
                draft,
                outlines,
                ctx,
                "Title",
                "g",
                "s",
                [],
                None,
                progress_callback=msgs.append,
            )
        assert len(msgs) > 0

    def test_generate_chapters_resume_from_batch(self):
        bg = self._make_generator(parallel=False, batch_size=1)
        outlines = [self._make_outline(i) for i in range(1, 4)]
        draft = StoryDraft(title="T", genre="g")
        ctx = StoryContext(total_chapters=3)
        chapter = self._make_chapter(3)
        bg.gen._write_chapter_with_long_context.return_value = chapter

        with patch(
            "pipeline.layer1_story.chapter_finalizer.process_chapter_post_write"
        ):
            result = bg.generate_chapters(
                draft,
                outlines,
                ctx,
                "T",
                "g",
                "s",
                [],
                None,
                resume_from_batch=2,  # skip first 2 batches
            )
        # Only batch 3 should run
        assert len(result) == 1

    def test_generate_chapters_with_checkpoint_callback(self):
        bg = self._make_generator(parallel=False, batch_size=2)
        outlines = [self._make_outline(i) for i in range(1, 3)]
        draft = StoryDraft(title="T", genre="g")
        ctx = StoryContext(total_chapters=2)
        bg.gen._write_chapter_with_long_context.side_effect = [
            self._make_chapter(1),
            self._make_chapter(2),
        ]
        checkpoint_calls = []

        with patch(
            "pipeline.layer1_story.chapter_finalizer.process_chapter_post_write"
        ):
            bg.generate_chapters(
                draft,
                outlines,
                ctx,
                "T",
                "g",
                "s",
                [],
                None,
                batch_checkpoint_callback=lambda idx, total: checkpoint_calls.append(
                    (idx, total)
                ),
            )
        assert len(checkpoint_calls) == 1
        assert checkpoint_calls[0] == (1, 1)

    def test_generate_chapters_checkpoint_callback_exception_ignored(self):
        bg = self._make_generator(parallel=False, batch_size=2)
        outlines = [self._make_outline(1)]
        draft = StoryDraft(title="T", genre="g")
        ctx = StoryContext(total_chapters=1)
        bg.gen._write_chapter_with_long_context.return_value = self._make_chapter(1)

        def bad_callback(idx, total):
            raise RuntimeError("checkpoint boom")

        with patch(
            "pipeline.layer1_story.chapter_finalizer.process_chapter_post_write"
        ):
            # Should not propagate the exception
            result = bg.generate_chapters(
                draft,
                outlines,
                ctx,
                "T",
                "g",
                "s",
                [],
                None,
                batch_checkpoint_callback=bad_callback,
            )
        assert len(result) == 1

    def test_generate_chapters_stream_callback_uses_sequential(self):
        bg = self._make_generator(
            parallel=True, batch_size=2
        )  # parallel=True but stream given
        outlines = [self._make_outline(1)]
        draft = StoryDraft(title="T", genre="g")
        ctx = StoryContext(total_chapters=1)
        bg.gen.write_chapter_stream.return_value = self._make_chapter(1)

        with patch(
            "pipeline.layer1_story.chapter_finalizer.process_chapter_post_write"
        ):
            result = bg.generate_chapters(
                draft,
                outlines,
                ctx,
                "T",
                "g",
                "s",
                [],
                None,
                stream_callback=lambda tok: None,
            )
        # stream_callback forces sequential path
        bg.gen.write_chapter_stream.assert_called_once()
        assert len(result) == 1

    def test_generate_chapters_token_budget_warning(self):
        bg = self._make_generator(parallel=False, batch_size=5)
        bg.gen.token_budget_per_chapter = 10  # tiny budget → triggers warning
        outlines = [self._make_outline(1)]
        draft = StoryDraft(title="T", genre="g")
        ctx = StoryContext(total_chapters=1)
        chapter = self._make_chapter(1)
        chapter.content = "x" * 400  # 100 estimated tokens >> budget of 10
        bg.gen._write_chapter_with_long_context.return_value = chapter

        with patch(
            "pipeline.layer1_story.chapter_finalizer.process_chapter_post_write"
        ):
            result = bg.generate_chapters(draft, outlines, ctx, "T", "g", "s", [], None)
        assert len(result) == 1

    def test_run_batch_parallel_success(self):
        bg = self._make_generator(parallel=True, batch_size=2)
        from pipeline.layer1_story.batch_generator import FrozenContext
        from concurrent.futures import ThreadPoolExecutor

        outlines = [self._make_outline(1), self._make_outline(2)]
        draft = StoryDraft(title="T", genre="g")
        ctx = StoryContext(total_chapters=2)
        frozen = FrozenContext(ctx, [])
        bg.gen._write_chapter_with_long_context.side_effect = [
            self._make_chapter(1),
            self._make_chapter(2),
        ]
        with patch(
            "pipeline.layer1_story.chapter_finalizer.process_chapter_post_write"
        ):
            with ThreadPoolExecutor(max_workers=3) as ex:
                chapters = bg._run_batch_parallel(
                    outlines,
                    frozen,
                    draft,
                    ctx,
                    [],
                    "T",
                    "g",
                    "s",
                    [],
                    None,
                    2000,
                    5,
                    False,
                    ex,
                    None,
                    None,
                )
        assert len(chapters) == 2
        assert chapters[0].chapter_number <= chapters[1].chapter_number

    def test_run_batch_parallel_raises_on_write_error(self):
        bg = self._make_generator(parallel=True, batch_size=2)
        from pipeline.layer1_story.batch_generator import FrozenContext
        from concurrent.futures import ThreadPoolExecutor

        outlines = [self._make_outline(1)]
        draft = StoryDraft(title="T", genre="g")
        ctx = StoryContext(total_chapters=1)
        frozen = FrozenContext(ctx, [])
        bg.gen._write_chapter_with_long_context.side_effect = RuntimeError(
            "write failed"
        )

        with patch(
            "pipeline.layer1_story.chapter_finalizer.process_chapter_post_write"
        ):
            with ThreadPoolExecutor(max_workers=3) as ex:
                with pytest.raises(RuntimeError, match="write failed"):
                    bg._run_batch_parallel(
                        outlines,
                        frozen,
                        draft,
                        ctx,
                        [],
                        "T",
                        "g",
                        "s",
                        [],
                        None,
                        2000,
                        5,
                        False,
                        ex,
                        None,
                        None,
                    )


# ===========================================================================
# services/seedream_client.py
# ===========================================================================


class TestSeedreamClient:
    def setup_method(self):
        with patch("services.seedream_client.os.makedirs"):
            from services.seedream_client import SeedreamClient

            self.client = SeedreamClient(
                api_key="test-key", base_url="https://api.test.com"
            )

    def test_is_configured_with_key(self):
        assert self.client.is_configured() is True

    def test_is_configured_without_key(self):
        with patch("services.seedream_client.os.makedirs"):
            from services.seedream_client import SeedreamClient

            c = SeedreamClient(api_key="", base_url="https://api.test.com")
        with patch.dict(os.environ, {}, clear=True):
            assert c.is_configured() is False

    def test_generate_character_reference_not_configured(self):
        with patch("services.seedream_client.os.makedirs"):
            from services.seedream_client import SeedreamClient

            c = SeedreamClient(api_key="", base_url="")
        result = c.generate_character_reference("Alice", "tall woman")
        assert result is None

    def test_generate_character_reference_success(self):
        self.client._text_to_image = MagicMock(return_value="/output/alice.png")
        result = self.client.generate_character_reference(
            "Alice", "tall woman with blue eyes"
        )
        assert result == "/output/alice.png"

    def test_generate_scene_no_references(self):
        self.client._text_to_image = MagicMock(return_value="/output/scene.png")
        result = self.client.generate_scene("A forest scene", [], "scene.png")
        assert result == "/output/scene.png"

    def test_generate_scene_with_references(self):
        self.client._edit_sequential = MagicMock(
            return_value="/output/scene_with_chars.png"
        )
        result = self.client.generate_scene(
            "A forest scene", ["/refs/char1.png"], "scene.png"
        )
        assert result == "/output/scene_with_chars.png"

    def test_generate_scene_not_configured(self):
        with patch("services.seedream_client.os.makedirs"):
            from services.seedream_client import SeedreamClient

            c = SeedreamClient(api_key="", base_url="")
        result = c.generate_scene("A scene", [], "f.png")
        assert result is None

    def test_text_to_image_success(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "data": [{"b64_json": base64.b64encode(b"fakeimage").decode()}]
        }

        with (
            patch("services.seedream_client.requests.post", return_value=mock_resp),
            patch.object(
                self.client, "_save_response_image", return_value="/out/img.png"
            ),
        ):
            result = self.client._text_to_image("A scene", "/out/img.png")
        assert result == "/out/img.png"

    def test_text_to_image_request_failure(self):
        with patch(
            "services.seedream_client.requests.post", side_effect=Exception("timeout")
        ):
            result = self.client._text_to_image("A scene", "/out/img.png")
        assert result is None

    def test_save_response_image_b64_json(self):
        img_bytes = b"PNG_IMAGE_DATA"
        b64 = base64.b64encode(img_bytes).decode()
        response = {"data": [{"b64_json": b64}]}
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test.png")
            result = self.client._save_response_image(response, output_path)
        assert result == output_path

    def test_save_response_image_base64_field(self):
        img_bytes = b"PNG_IMAGE_DATA"
        b64 = base64.b64encode(img_bytes).decode()
        response = {"data": [{"base64": b64}]}
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test.png")
            result = self.client._save_response_image(response, output_path)
        assert result == output_path

    def test_save_response_image_url(self):
        mock_resp = MagicMock()
        mock_resp.content = b"PNG_DATA"
        response = {"data": [{"url": "https://example.com/img.png"}]}
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test.png")
            with patch("services.seedream_client.requests.get", return_value=mock_resp):
                result = self.client._save_response_image(response, output_path)
        assert result == output_path

    def test_save_response_image_empty_data(self):
        result = self.client._save_response_image({"data": []}, "/out/img.png")
        assert result is None

    def test_save_response_image_results_key(self):
        img_bytes = b"DATA"
        b64 = base64.b64encode(img_bytes).decode()
        response = {"results": [{"b64_json": b64}]}
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test.png")
            result = self.client._save_response_image(response, output_path)
        assert result == output_path

    def test_save_response_image_unknown_format(self):
        response = {"data": [{"unknown_key": "value"}]}
        result = self.client._save_response_image(response, "/out/img.png")
        assert result is None

    def test_edit_sequential_no_valid_refs_falls_back(self):
        self.client._text_to_image = MagicMock(return_value="/out/fallback.png")
        result = self.client._edit_sequential(
            "prompt", ["/nonexistent/ref.png"], "/out/img.png"
        )
        self.client._text_to_image.assert_called_once()
        assert result == "/out/fallback.png"

    def test_edit_sequential_with_valid_ref(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ref_path = os.path.join(tmpdir, "ref.png")
            with open(ref_path, "wb") as f:
                f.write(b"PNG")

            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = {
                "data": [{"b64_json": base64.b64encode(b"img").decode()}]
            }

            with (
                patch("services.seedream_client.requests.post", return_value=mock_resp),
                patch.object(
                    self.client, "_save_response_image", return_value=ref_path
                ),
            ):
                result = self.client._edit_sequential("scene", [ref_path], ref_path)
        assert result == ref_path

    def test_edit_sequential_request_failure_falls_back(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ref_path = os.path.join(tmpdir, "ref.png")
            with open(ref_path, "wb") as f:
                f.write(b"PNG")
            self.client._text_to_image = MagicMock(return_value="/fallback.png")
            with patch(
                "services.seedream_client.requests.post", side_effect=Exception("fail")
            ):
                result = self.client._edit_sequential(
                    "scene", [ref_path], "/out/img.png"
                )
        assert result == "/fallback.png"

    def test_edit_sequential_skips_large_refs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ref_path = os.path.join(tmpdir, "big.png")
            with open(ref_path, "wb") as f:
                f.write(b"PNG")
            self.client._text_to_image = MagicMock(return_value="/fallback.png")
            # Mock os.path.getsize to return > MAX_REF_SIZE
            with patch(
                "services.seedream_client.os.path.getsize",
                return_value=20 * 1024 * 1024,
            ):
                result = self.client._edit_sequential(
                    "scene", [ref_path], "/out/img.png"
                )
        # All refs skipped → falls back to text_to_image
        assert result == "/fallback.png"

    def test_batch_generate_empty(self):
        assert self.client.batch_generate([]) == []

    def test_batch_generate_success(self):
        self.client.generate_scene = MagicMock(return_value="/out/scene.png")
        reqs = [
            {"scene_prompt": "scene1", "reference_images": [], "filename": "s1.png"},
            {"scene_prompt": "scene2", "reference_images": [], "filename": "s2.png"},
        ]
        results = self.client.batch_generate(reqs)
        assert len(results) == 2
        assert all(r.success for r in results)

    def test_batch_generate_partial_failure(self):
        def gen(**kwargs):
            if "scene2" in kwargs.get("scene_prompt", ""):
                raise Exception("gen failed")
            return "/out/scene.png"

        self.client.generate_scene = gen
        reqs = [
            {"scene_prompt": "scene1", "reference_images": [], "filename": "s1.png"},
            {"scene_prompt": "scene2", "reference_images": [], "filename": "s2.png"},
        ]
        results = self.client.batch_generate(reqs)
        assert len(results) == 2
        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]
        assert len(successes) == 1
        assert len(failures) == 1


# ===========================================================================
# services/replicate_ip_adapter.py
# ===========================================================================


class TestReplicateIPAdapter:
    def setup_method(self):
        with (
            patch("services.replicate_ip_adapter.ConfigManager") as MockCfg,
            patch("services.replicate_ip_adapter.os.makedirs"),
        ):
            MockCfg.return_value.pipeline.replicate_api_key = "test-key"
            from services.replicate_ip_adapter import ReplicateIPAdapter

            self.adapter = ReplicateIPAdapter(api_key="test-key")

    def test_is_configured_with_key(self):
        assert self.adapter.is_configured() is True

    def test_is_configured_without_key(self):
        with (
            patch("services.replicate_ip_adapter.ConfigManager") as MockCfg,
            patch("services.replicate_ip_adapter.os.makedirs"),
        ):
            MockCfg.return_value.pipeline.replicate_api_key = ""
            from services.replicate_ip_adapter import ReplicateIPAdapter

            a = ReplicateIPAdapter(api_key="")
        assert a.is_configured() is False

    def test_generate_not_configured(self):
        with (
            patch("services.replicate_ip_adapter.ConfigManager") as MockCfg,
            patch("services.replicate_ip_adapter.os.makedirs"),
        ):
            MockCfg.return_value.pipeline.replicate_api_key = ""
            from services.replicate_ip_adapter import ReplicateIPAdapter

            a = ReplicateIPAdapter(api_key="")
        result = a.generate("prompt", "ref.png")
        assert result is None

    def test_generate_ref_not_found(self):
        result = self.adapter.generate("prompt", "/nonexistent/ref.png")
        assert result is None

    def test_generate_success_list_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ref = os.path.join(tmpdir, "ref.png")
            with open(ref, "wb") as f:
                f.write(b"PNG")

            # Mock: create prediction, poll → succeeded, download image
            create_resp = MagicMock()
            create_resp.raise_for_status.return_value = None
            create_resp.json.return_value = {
                "urls": {"get": "https://api.replicate.com/v1/predictions/abc"},
                "status": "starting",
            }
            poll_resp = MagicMock()
            poll_resp.raise_for_status.return_value = None
            poll_resp.json.return_value = {
                "status": "succeeded",
                "output": ["https://delivery.replicate.com/img.png"],
            }
            img_resp = MagicMock()
            img_resp.raise_for_status.return_value = None
            img_resp.content = b"IMAGE_BYTES"

            output_dir = os.path.join(tmpdir, "output", "images")
            os.makedirs(output_dir, exist_ok=True)
            self.adapter.output_dir = output_dir

            with (
                patch(
                    "services.replicate_ip_adapter.requests.post",
                    return_value=create_resp,
                ),
                patch(
                    "services.replicate_ip_adapter.requests.get",
                    side_effect=[poll_resp, img_resp],
                ),
                patch("services.replicate_ip_adapter.time.sleep"),
                patch(
                    "services.replicate_ip_adapter.time.time", side_effect=[0, 5, 10]
                ),
            ):
                result = self.adapter.generate(
                    "A portrait", ref, "output.png", timeout=120
                )

        assert result is not None

    def test_generate_prediction_failed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ref = os.path.join(tmpdir, "ref.png")
            with open(ref, "wb") as f:
                f.write(b"PNG")

            create_resp = MagicMock()
            create_resp.raise_for_status.return_value = None
            create_resp.json.return_value = {
                "urls": {"get": "https://api.replicate.com/v1/predictions/abc"},
            }
            poll_resp = MagicMock()
            poll_resp.raise_for_status.return_value = None
            poll_resp.json.return_value = {"status": "failed", "error": "GPU error"}

            with (
                patch(
                    "services.replicate_ip_adapter.requests.post",
                    return_value=create_resp,
                ),
                patch(
                    "services.replicate_ip_adapter.requests.get", return_value=poll_resp
                ),
                patch("services.replicate_ip_adapter.time.sleep"),
                patch(
                    "services.replicate_ip_adapter.time.time", side_effect=[0, 5, 10]
                ),
            ):
                result = self.adapter.generate(
                    "A portrait", ref, "output.png", timeout=120
                )

        assert result is None

    def test_generate_no_poll_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ref = os.path.join(tmpdir, "ref.png")
            with open(ref, "wb") as f:
                f.write(b"PNG")

            create_resp = MagicMock()
            create_resp.raise_for_status.return_value = None
            create_resp.json.return_value = {"urls": {}}  # no 'get' key

            with patch(
                "services.replicate_ip_adapter.requests.post", return_value=create_resp
            ):
                result = self.adapter.generate("prompt", ref)
        assert result is None

    def test_generate_timeout(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ref = os.path.join(tmpdir, "ref.png")
            with open(ref, "wb") as f:
                f.write(b"PNG")

            create_resp = MagicMock()
            create_resp.raise_for_status.return_value = None
            create_resp.json.return_value = {
                "urls": {"get": "https://api.replicate.com/v1/predictions/abc"},
            }
            poll_resp = MagicMock()
            poll_resp.raise_for_status.return_value = None
            poll_resp.json.return_value = {"status": "processing"}

            # Return 0 for start, then 999 for all subsequent calls (exceeds timeout=5)
            _time_values = iter([0] + [999] * 100)
            with (
                patch(
                    "services.replicate_ip_adapter.requests.post",
                    return_value=create_resp,
                ),
                patch(
                    "services.replicate_ip_adapter.requests.get", return_value=poll_resp
                ),
                patch("services.replicate_ip_adapter.time.sleep"),
                patch(
                    "services.replicate_ip_adapter.time.time", side_effect=_time_values
                ),
            ):
                result = self.adapter.generate("prompt", ref, timeout=5)
        assert result is None

    def test_generate_request_exception(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ref = os.path.join(tmpdir, "ref.png")
            with open(ref, "wb") as f:
                f.write(b"PNG")
            with patch(
                "services.replicate_ip_adapter.requests.post",
                side_effect=Exception("network"),
            ):
                result = self.adapter.generate("prompt", ref)
        assert result is None

    def test_generate_string_output(self):
        """Test handling of string (not list) output format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ref = os.path.join(tmpdir, "ref.png")
            with open(ref, "wb") as f:
                f.write(b"PNG")

            create_resp = MagicMock()
            create_resp.raise_for_status.return_value = None
            create_resp.json.return_value = {
                "urls": {"get": "https://api.replicate.com/v1/predictions/abc"},
            }
            poll_resp = MagicMock()
            poll_resp.raise_for_status.return_value = None
            poll_resp.json.return_value = {
                "status": "succeeded",
                "output": "https://delivery.replicate.com/img.png",  # string, not list
            }
            img_resp = MagicMock()
            img_resp.raise_for_status.return_value = None
            img_resp.content = b"IMG"

            output_dir = os.path.join(tmpdir, "out")
            os.makedirs(output_dir)
            self.adapter.output_dir = output_dir

            with (
                patch(
                    "services.replicate_ip_adapter.requests.post",
                    return_value=create_resp,
                ),
                patch(
                    "services.replicate_ip_adapter.requests.get",
                    side_effect=[poll_resp, img_resp],
                ),
                patch("services.replicate_ip_adapter.time.sleep"),
                patch(
                    "services.replicate_ip_adapter.time.time", side_effect=[0, 5, 10]
                ),
            ):
                result = self.adapter.generate("prompt", ref, timeout=120)
        assert result is not None

    def test_generate_unexpected_output_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ref = os.path.join(tmpdir, "ref.png")
            with open(ref, "wb") as f:
                f.write(b"PNG")

            create_resp = MagicMock()
            create_resp.raise_for_status.return_value = None
            create_resp.json.return_value = {
                "urls": {"get": "https://api.replicate.com/v1/predictions/abc"},
            }
            poll_resp = MagicMock()
            poll_resp.raise_for_status.return_value = None
            poll_resp.json.return_value = {
                "status": "succeeded",
                "output": {"unexpected": "dict"},  # neither list nor str
            }

            with (
                patch(
                    "services.replicate_ip_adapter.requests.post",
                    return_value=create_resp,
                ),
                patch(
                    "services.replicate_ip_adapter.requests.get", return_value=poll_resp
                ),
                patch("services.replicate_ip_adapter.time.sleep"),
                patch(
                    "services.replicate_ip_adapter.time.time", side_effect=[0, 5, 10]
                ),
            ):
                result = self.adapter.generate("prompt", ref, timeout=120)
        assert result is None

    def test_mime_type_jpg(self):
        """Ensure .jpg files are correctly identified for MIME type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ref = os.path.join(tmpdir, "ref.jpg")
            with open(ref, "wb") as f:
                f.write(b"JPEG")

            create_resp = MagicMock()
            create_resp.raise_for_status.return_value = None
            create_resp.json.return_value = {"urls": {}}

            with patch(
                "services.replicate_ip_adapter.requests.post", return_value=create_resp
            ):
                result = self.adapter.generate("prompt", ref)
        # No poll URL → None, but mime detection shouldn't crash
        assert result is None

    def test_batch_generate_empty(self):
        assert self.adapter.batch_generate([]) == []

    def test_batch_generate_success(self):
        self.adapter.generate = MagicMock(return_value="/out/img.png")
        reqs = [
            {
                "prompt": "p1",
                "reference_image_path": "/refs/r1.png",
                "filename": "f1.png",
            },
            {
                "prompt": "p2",
                "reference_image_path": "/refs/r2.png",
                "filename": "f2.png",
            },
        ]
        results = self.adapter.batch_generate(reqs)
        assert len(results) == 2
        assert all(r.success for r in results)

    def test_batch_generate_partial_failure(self):
        def gen(**kwargs):
            if "p2" in kwargs.get("prompt", ""):
                raise Exception("failed")
            return "/out/img.png"

        self.adapter.generate = gen
        reqs = [
            {"prompt": "p1", "reference_image_path": "/r1.png"},
            {"prompt": "p2", "reference_image_path": "/r2.png"},
        ]
        results = self.adapter.batch_generate(reqs)
        assert len(results) == 2
        failures = [r for r in results if not r.success]
        assert len(failures) == 1
