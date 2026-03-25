"""Tests for Phase 16 agent debate_response overrides."""
import pytest
from unittest.mock import patch, MagicMock
from models.schemas import AgentReview, DebateEntry, DebateStance


def _make_review(agent_name, score=0.7, issues=None, suggestions=None):
    return AgentReview(
        agent_role="test",
        agent_name=agent_name,
        score=score,
        issues=issues or [],
        suggestions=suggestions or [],
    )


class TestBaseAgentDebateDefault:
    def test_default_returns_empty_list(self):
        from pipeline.agents.base_agent import BaseAgent

        class ConcreteAgent(BaseAgent):
            name = "TestAgent"
            role = "test"
            layers = [1]

            def review(self, output, layer, iteration, prior_reviews=None):
                return None

        with patch("pipeline.agents.base_agent.LLMClient"):
            agent = ConcreteAgent()

        story_draft = MagicMock()
        reviews = [_make_review("OtherAgent")]
        own_review = _make_review("TestAgent")
        result = agent.debate_response(story_draft, 1, own_review, reviews)
        assert result == []


class TestDramaCriticDebate:
    def _make_agent(self):
        with patch("pipeline.agents.base_agent.LLMClient"):
            from pipeline.agents.drama_critic import DramaCriticAgent
            return DramaCriticAgent()

    def test_challenge_on_low_drama_suggestion(self):
        agent = self._make_agent()
        story_draft = MagicMock()
        story_draft.genre = "tien_hiep"
        own_review = _make_review(agent.name)
        other_review = _make_review(
            "OtherAgent",
            suggestions=["Cần giảm xung đột trong chương 3 để giữ nhịp"],
        )
        entries = agent.debate_response(story_draft, 2, own_review, [own_review, other_review])
        assert len(entries) >= 1
        challenge = entries[0]
        assert challenge.stance == DebateStance.CHALLENGE
        assert challenge.target_agent == "OtherAgent"
        assert "tien_hiep" in challenge.reasoning

    def test_no_trigger_returns_empty(self):
        agent = self._make_agent()
        story_draft = MagicMock()
        story_draft.genre = "tien_hiep"
        own_review = _make_review(agent.name)
        other_review = _make_review(
            "OtherAgent",
            suggestions=["Cải thiện văn phong đoạn mô tả cảnh sắc"],
        )
        entries = agent.debate_response(story_draft, 2, own_review, [own_review, other_review])
        assert entries == []

    def test_skips_own_review(self):
        agent = self._make_agent()
        story_draft = MagicMock()
        story_draft.genre = "tien_hiep"
        own_review = _make_review(agent.name, suggestions=["Giảm xung đột ở cuối"])
        entries = agent.debate_response(story_draft, 2, own_review, [own_review])
        # Own review should not trigger a challenge against itself
        assert all(e.target_agent != agent.name for e in entries)


class TestCharacterSpecialistDebate:
    def _make_agent(self):
        with patch("pipeline.agents.base_agent.LLMClient"):
            from pipeline.agents.character_specialist import CharacterSpecialistAgent
            return CharacterSpecialistAgent()

    def test_challenge_on_character_break_issue(self):
        agent = self._make_agent()
        story_draft = MagicMock()
        own_review = _make_review(agent.name)
        other_review = _make_review(
            "DramaCritic",
            issues=["Nhân vật phản bội đột ngột không có foreshadowing"],
        )
        entries = agent.debate_response(story_draft, 2, own_review, [own_review, other_review])
        assert len(entries) >= 1
        challenge = entries[0]
        assert challenge.stance == DebateStance.CHALLENGE
        assert challenge.target_agent == "DramaCritic"
        assert "foreshadowing" in challenge.reasoning

    def test_no_trigger_returns_empty(self):
        agent = self._make_agent()
        story_draft = MagicMock()
        own_review = _make_review(agent.name)
        other_review = _make_review(
            "DramaCritic",
            issues=["Cần thêm mô tả chi tiết về bối cảnh"],
        )
        entries = agent.debate_response(story_draft, 2, own_review, [own_review, other_review])
        assert entries == []

    def test_skips_own_review(self):
        agent = self._make_agent()
        story_draft = MagicMock()
        own_review = _make_review(agent.name, issues=["thay đổi tính cách đột ngột"])
        entries = agent.debate_response(story_draft, 2, own_review, [own_review])
        assert all(e.target_agent != agent.name for e in entries)
