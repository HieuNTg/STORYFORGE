"""Tests for Phase 16 debate orchestrator."""
import pytest
from unittest.mock import MagicMock
from models.schemas import AgentReview, DebateEntry, DebateStance
from pipeline.agents.debate_orchestrator import (
    DebateOrchestrator,
    _find_review,
    _merge_debate_into_reviews,
)


def _make_review(agent_name, score=0.7, issues=None, suggestions=None):
    return AgentReview(
        agent_role="test",
        agent_name=agent_name,
        score=score,
        issues=issues or [],
        suggestions=suggestions or [],
    )


def _make_agent(name, debate_entries=None):
    agent = MagicMock()
    agent.name = name
    agent.debate_response.return_value = debate_entries or []
    return agent


class TestFindReview:
    def test_finds_matching_review(self):
        reviews = [_make_review("AgentA"), _make_review("AgentB")]
        result = _find_review(reviews, "AgentA")
        assert result is not None
        assert result.agent_name == "AgentA"

    def test_returns_none_when_not_found(self):
        reviews = [_make_review("AgentA")]
        result = _find_review(reviews, "AgentZ")
        assert result is None

    def test_empty_reviews(self):
        assert _find_review([], "AgentA") is None


class TestMergeDebateIntoReviews:
    def test_no_entries_returns_originals(self):
        reviews = [_make_review("AgentA", score=0.8)]
        merged = _merge_debate_into_reviews(reviews, [])
        assert len(merged) == 1
        assert merged[0].score == 0.8

    def test_revised_score_averaged(self):
        reviews = [_make_review("AgentA", score=0.8)]
        entry = DebateEntry(
            agent_name="AgentB",
            stance=DebateStance.CHALLENGE,
            target_agent="AgentA",
            revised_score=0.4,
        )
        merged = _merge_debate_into_reviews(reviews, [entry])
        assert len(merged) == 1
        # (0.8 + 0.4) / 2 = 0.6
        assert merged[0].score == pytest.approx(0.6)

    def test_reasoning_appended_to_suggestions(self):
        reviews = [_make_review("AgentA")]
        entry = DebateEntry(
            agent_name="AgentB",
            stance=DebateStance.CHALLENGE,
            target_agent="AgentA",
            reasoning="Drama reduction is wrong.",
        )
        merged = _merge_debate_into_reviews(reviews, [entry])
        assert any("[Debate-AgentB]" in s for s in merged[0].suggestions)

    def test_unknown_target_agent_ignored(self):
        reviews = [_make_review("AgentA")]
        entry = DebateEntry(
            agent_name="AgentB",
            target_agent="UnknownAgent",
            reasoning="Some reasoning.",
        )
        # Should not raise
        merged = _merge_debate_into_reviews(reviews, [entry])
        assert len(merged) == 1

    def test_no_revised_score_skips_score_change(self):
        reviews = [_make_review("AgentA", score=0.9)]
        entry = DebateEntry(
            agent_name="AgentB",
            target_agent="AgentA",
            reasoning="Some reasoning.",
            revised_score=None,
        )
        merged = _merge_debate_into_reviews(reviews, [entry])
        assert merged[0].score == pytest.approx(0.9)


class TestDebateOrchestrator:
    def test_no_challenges_skips_debate(self):
        orchestrator = DebateOrchestrator(max_rounds=3)
        reviews = [_make_review("AgentA"), _make_review("AgentB")]
        agents = [_make_agent("AgentA"), _make_agent("AgentB")]
        story_draft = MagicMock()
        story_draft.genre = "tien_hiep"

        result = orchestrator.run_debate(agents, story_draft, layer=2, round1_reviews=reviews)

        assert result.debate_skipped is True
        assert result.total_challenges == 0
        assert result.final_reviews == reviews

    def test_with_challenges_runs_rebuttal(self):
        orchestrator = DebateOrchestrator(max_rounds=3)
        reviews = [_make_review("AgentA"), _make_review("AgentB")]
        challenge_entry = DebateEntry(
            agent_name="AgentA",
            round_number=2,
            stance=DebateStance.CHALLENGE,
            target_agent="AgentB",
            reasoning="Disagree.",
        )
        agents = [
            _make_agent("AgentA", debate_entries=[challenge_entry]),
            _make_agent("AgentB"),
        ]
        story_draft = MagicMock()

        result = orchestrator.run_debate(agents, story_draft, layer=2, round1_reviews=reviews)

        assert result.debate_skipped is False
        assert result.total_challenges == 1
        assert len(result.rounds) == 3  # round1(empty), round2, round3

    def test_consensus_score_calculated(self):
        orchestrator = DebateOrchestrator(max_rounds=3)
        reviews = [_make_review("AgentA", score=0.8), _make_review("AgentB", score=0.6)]
        challenge_entry = DebateEntry(
            agent_name="AgentA",
            round_number=2,
            stance=DebateStance.CHALLENGE,
            target_agent="AgentB",
            reasoning="Needs more drama.",
        )
        agents = [
            _make_agent("AgentA", debate_entries=[challenge_entry]),
            _make_agent("AgentB"),
        ]
        story_draft = MagicMock()

        result = orchestrator.run_debate(agents, story_draft, layer=2, round1_reviews=reviews)

        assert 0.0 <= result.consensus_score <= 1.0

    def test_progress_callback_called(self):
        orchestrator = DebateOrchestrator(max_rounds=3)
        reviews = [_make_review("AgentA")]
        challenge_entry = DebateEntry(
            agent_name="AgentA",
            stance=DebateStance.CHALLENGE,
            target_agent="AgentX",
            reasoning="Issue.",
        )
        agents = [_make_agent("AgentA", debate_entries=[challenge_entry])]
        story_draft = MagicMock()
        callback = MagicMock()

        orchestrator.run_debate(
            agents, story_draft, layer=2, round1_reviews=reviews, progress_callback=callback
        )

        callback.assert_called()

    def test_agent_without_review_skipped(self):
        orchestrator = DebateOrchestrator(max_rounds=3)
        # Only AgentA has a review; AgentB has no review in round1
        reviews = [_make_review("AgentA")]
        agents = [_make_agent("AgentA"), _make_agent("AgentB")]
        story_draft = MagicMock()

        orchestrator.run_debate(agents, story_draft, layer=2, round1_reviews=reviews)

        # AgentB had no own_review, so debate_response not called for AgentB
        agents[1].debate_response.assert_not_called()
