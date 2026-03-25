"""Tests for Phase 16 debate schemas — DebateStance, DebateEntry, DebateResult."""
import pytest
from models.schemas import AgentReview, DebateEntry, DebateResult, DebateStance


class TestDebateStance:
    def test_challenge_value(self):
        assert DebateStance.CHALLENGE == "challenge"

    def test_support_value(self):
        assert DebateStance.SUPPORT == "support"

    def test_neutral_value(self):
        assert DebateStance.NEUTRAL == "neutral"

    def test_is_str_enum(self):
        assert isinstance(DebateStance.CHALLENGE, str)


class TestDebateEntry:
    def test_defaults(self):
        entry = DebateEntry(agent_name="AgentA")
        assert entry.round_number == 1
        assert entry.stance == DebateStance.NEUTRAL
        assert entry.target_agent == ""
        assert entry.target_issue == ""
        assert entry.reasoning == ""
        assert entry.revised_score is None

    def test_challenge_entry(self):
        entry = DebateEntry(
            agent_name="DramaCritic",
            round_number=2,
            stance=DebateStance.CHALLENGE,
            target_agent="CharacterAgent",
            target_issue="giảm kịch tính",
            reasoning="Drama level is appropriate.",
            revised_score=0.7,
        )
        assert entry.stance == DebateStance.CHALLENGE
        assert entry.revised_score == 0.7
        assert entry.round_number == 2

    def test_support_entry(self):
        entry = DebateEntry(
            agent_name="AgentB",
            stance=DebateStance.SUPPORT,
            target_agent="AgentA",
            reasoning="Agree with assessment.",
        )
        assert entry.stance == DebateStance.SUPPORT


class TestDebateResult:
    def test_empty_defaults(self):
        result = DebateResult()
        assert result.rounds == []
        assert result.final_reviews == []
        assert result.consensus_score == 0.0
        assert result.total_challenges == 0
        assert result.debate_skipped is False

    def test_skipped_debate(self):
        review = AgentReview(
            agent_role="test",
            agent_name="AgentA",
            score=0.8,
        )
        result = DebateResult(
            rounds=[[], []],
            final_reviews=[review],
            debate_skipped=True,
            total_challenges=0,
        )
        assert result.debate_skipped is True
        assert len(result.final_reviews) == 1

    def test_with_challenges(self):
        entry = DebateEntry(
            agent_name="AgentA",
            round_number=2,
            stance=DebateStance.CHALLENGE,
            target_agent="AgentB",
        )
        result = DebateResult(
            rounds=[[], [entry]],
            total_challenges=1,
            consensus_score=0.75,
        )
        assert result.total_challenges == 1
        assert result.consensus_score == 0.75
        assert result.rounds[1][0].stance == DebateStance.CHALLENGE
