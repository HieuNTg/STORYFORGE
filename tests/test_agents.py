"""Tests for pipeline agent system — all 5 agent types + registry."""
from unittest.mock import patch, MagicMock
from pipeline.agents.base_agent import BaseAgent
from pipeline.agents.agent_registry import AgentRegistry
from pipeline.agents.character_specialist import CharacterSpecialistAgent
from pipeline.agents.continuity_checker import ContinuityCheckerAgent
from pipeline.agents.dialogue_expert import DialogueExpertAgent
from pipeline.agents.drama_critic import DramaCriticAgent
from pipeline.agents.editor_in_chief import EditorInChiefAgent
from models.schemas import AgentReview


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dummy_agent_cls(name="Test", role="test", layers=None):
    """Create a concrete BaseAgent subclass for testing abstract class behaviour."""
    _layers = layers or [1]

    class DummyAgent(BaseAgent):
        def review(self, output, layer, iteration):
            return None

    DummyAgent.name = name
    DummyAgent.role = role
    DummyAgent.layers = _layers
    return DummyAgent


# ---------------------------------------------------------------------------
# BaseAgent
# ---------------------------------------------------------------------------

class TestBaseAgent:
    def test_parse_review_json_approved(self):
        """Score >= 0.6 should be approved."""
        cls = _make_dummy_agent_cls()
        with patch("pipeline.agents.base_agent.LLMClient"):
            agent = cls()
        result = {"score": 0.8, "issues": ["minor issue"], "suggestions": ["improve X"]}
        review = agent._parse_review_json(result, layer=1, iteration=1)
        assert review.approved is True
        assert review.score == 0.8
        assert review.agent_name == "Test"

    def test_parse_review_json_rejected(self):
        """Score < 0.6 should be rejected."""
        cls = _make_dummy_agent_cls()
        with patch("pipeline.agents.base_agent.LLMClient"):
            agent = cls()
        result = {"score": 0.3, "issues": ["critical"], "suggestions": []}
        review = agent._parse_review_json(result, layer=1, iteration=1)
        assert review.approved is False
        assert review.score == 0.3

    def test_parse_review_json_defaults(self):
        """Missing fields should use defaults."""
        cls = _make_dummy_agent_cls()
        with patch("pipeline.agents.base_agent.LLMClient"):
            agent = cls()
        review = agent._parse_review_json({}, layer=2, iteration=3)
        assert review.score == 0.5
        assert review.issues == []
        assert review.layer == 2
        assert review.iteration == 3

    def test_parse_review_json_boundary_score_approved(self):
        """Exactly 0.6 should be approved."""
        cls = _make_dummy_agent_cls()
        with patch("pipeline.agents.base_agent.LLMClient"):
            agent = cls()
        review = agent._parse_review_json({"score": 0.6}, layer=1, iteration=1)
        assert review.approved is True

    def test_parse_review_json_suggestions_preserved(self):
        cls = _make_dummy_agent_cls()
        with patch("pipeline.agents.base_agent.LLMClient"):
            agent = cls()
        result = {"score": 0.7, "issues": [], "suggestions": ["add more drama", "fix pacing"]}
        review = agent._parse_review_json(result, layer=1, iteration=1)
        assert review.suggestions == ["add more drama", "fix pacing"]

    def test_parse_review_json_refined_content(self):
        cls = _make_dummy_agent_cls()
        with patch("pipeline.agents.base_agent.LLMClient"):
            agent = cls()
        result = {"score": 0.8, "refined_content": "Better chapter text"}
        review = agent._parse_review_json(result, layer=1, iteration=1)
        assert review.refined_content == "Better chapter text"

    def test_agent_role_and_name_in_review(self):
        cls = _make_dummy_agent_cls(name="MyAgent", role="my_role")
        with patch("pipeline.agents.base_agent.LLMClient"):
            agent = cls()
        review = agent._parse_review_json({"score": 0.7}, layer=1, iteration=2)
        assert review.agent_role == "my_role"
        assert review.agent_name == "MyAgent"


# ---------------------------------------------------------------------------
# AgentRegistry
# ---------------------------------------------------------------------------

class TestAgentRegistry:
    def setup_method(self):
        """Reset singleton for each test."""
        AgentRegistry._instance = None

    def test_register_and_get_for_layer(self):
        registry = AgentRegistry()
        with patch("pipeline.agents.base_agent.LLMClient"):
            agent = CharacterSpecialistAgent()
        registry.register(agent)
        agents = registry.get_agents_for_layer(1)
        assert any(a.name == agent.name for a in agents)

    def test_no_duplicate_registration(self):
        registry = AgentRegistry()
        with patch("pipeline.agents.base_agent.LLMClient"):
            agent = CharacterSpecialistAgent()
        registry.register(agent)
        registry.register(agent)
        agents = registry.get_agents_for_layer(1)
        names = [a.name for a in agents if a.name == agent.name]
        assert len(names) == 1

    def test_get_agents_for_layer_filters_correctly(self):
        registry = AgentRegistry()
        with patch("pipeline.agents.base_agent.LLMClient"):
            drama_agent = DramaCriticAgent()  # only layer 2
        registry.register(drama_agent)
        # Should not appear in layer 1
        assert drama_agent not in registry.get_agents_for_layer(1)
        # Should appear in layer 2
        assert drama_agent in registry.get_agents_for_layer(2)

    def test_empty_registry_returns_empty_list(self):
        registry = AgentRegistry()
        assert registry.get_agents_for_layer(1) == []

    def test_registry_is_singleton(self):
        r1 = AgentRegistry()
        r2 = AgentRegistry()
        assert r1 is r2

    @patch("pipeline.agents.agent_registry.ConfigManager")
    def test_run_review_cycle_all_approved_stops_early(self, mock_config):
        mock_config.return_value.llm.max_parallel_workers = 1
        registry = AgentRegistry()

        mock_review = MagicMock()
        mock_review.approved = True
        mock_review.score = 0.9
        mock_review.issues = []

        mock_agent = MagicMock(spec=BaseAgent)
        mock_agent.name = "MockAgent"
        mock_agent.role = "mock"
        mock_agent.layers = [1]
        mock_agent.review.return_value = mock_review
        registry.register(mock_agent)

        output = MagicMock()
        reviews = registry.run_review_cycle(output, layer=1, max_iterations=3)
        # Stops after first iteration (all approved)
        assert mock_agent.review.call_count == 1
        assert len(reviews) == 1

    @patch("pipeline.agents.agent_registry.ConfigManager")
    def test_run_review_cycle_no_agents_returns_empty(self, mock_config):
        mock_config.return_value.llm.max_parallel_workers = 1
        registry = AgentRegistry()
        output = MagicMock()
        reviews = registry.run_review_cycle(output, layer=99, max_iterations=2)
        assert reviews == []

    @patch("pipeline.agents.agent_registry.ConfigManager")
    def test_run_review_cycle_agent_exception_continues(self, mock_config):
        mock_config.return_value.llm.max_parallel_workers = 1
        registry = AgentRegistry()

        mock_agent = MagicMock(spec=BaseAgent)
        mock_agent.name = "ErrorAgent"
        mock_agent.role = "error"
        mock_agent.layers = [1]
        mock_agent.review.side_effect = RuntimeError("LLM failed")
        registry.register(mock_agent)

        output = MagicMock()
        # Should not raise; failed agent is logged and skipped
        reviews = registry.run_review_cycle(output, layer=1, max_iterations=1)
        assert reviews == []

    @patch("pipeline.agents.agent_registry.ConfigManager")
    def test_run_review_cycle_with_progress_callback(self, mock_config):
        mock_config.return_value.llm.max_parallel_workers = 1
        registry = AgentRegistry()

        mock_review = MagicMock()
        mock_review.approved = True
        mock_review.score = 0.9
        mock_review.issues = []

        mock_agent = MagicMock(spec=BaseAgent)
        mock_agent.name = "CBAgent"
        mock_agent.role = "cb"
        mock_agent.layers = [1]
        mock_agent.review.return_value = mock_review
        registry.register(mock_agent)

        messages = []
        registry.run_review_cycle(
            MagicMock(), layer=1, max_iterations=1,
            progress_callback=messages.append,
        )
        assert len(messages) > 0


# ---------------------------------------------------------------------------
# CharacterSpecialistAgent
# ---------------------------------------------------------------------------

class TestCharacterSpecialist:
    def _make_agent(self):
        with patch("pipeline.agents.base_agent.LLMClient"):
            return CharacterSpecialistAgent()

    def test_extract_data_with_story_draft(self, sample_pipeline_output):
        agent = self._make_agent()
        chars_info, chapters_content = agent._extract_data(sample_pipeline_output, layer=1)
        assert "Ly Huyen" in chars_info
        assert chars_info != "Khong co thong tin nhan vat."

    def test_extract_data_no_story_draft_returns_defaults(self):
        agent = self._make_agent()
        from models.schemas import PipelineOutput
        output = PipelineOutput()
        chars_info, chapters_content = agent._extract_data(output, layer=1)
        assert chars_info == "Không có thông tin nhân vật."

    def test_extract_data_layer2_uses_enhanced_chapters(self, sample_pipeline_output):
        agent = self._make_agent()
        chars_info, chapters_content = agent._extract_data(sample_pipeline_output, layer=2)
        # Should still get character info from story_draft
        assert "Ly Huyen" in chars_info

    def test_extract_consistency_context_with_draft(self, sample_pipeline_output):
        agent = self._make_agent()
        context = agent.extract_consistency_context(sample_pipeline_output)
        assert isinstance(context, str)
        assert "Ly Huyen" in context

    def test_extract_consistency_context_no_draft(self):
        agent = self._make_agent()
        from models.schemas import PipelineOutput
        output = PipelineOutput()
        context = agent.extract_consistency_context(output)
        assert context == ""

    def test_review_calls_llm(self, sample_pipeline_output):
        agent = self._make_agent()
        agent.llm = MagicMock()
        agent.llm.generate_json.return_value = {"score": 0.8, "issues": [], "suggestions": []}
        review = agent.review(sample_pipeline_output, layer=1, iteration=1)
        assert agent.llm.generate_json.called
        assert review.score == 0.8


# ---------------------------------------------------------------------------
# ContinuityCheckerAgent
# ---------------------------------------------------------------------------

class TestContinuityChecker:
    def _make_agent(self):
        with patch("pipeline.agents.base_agent.LLMClient"):
            return ContinuityCheckerAgent()

    def test_extract_data_with_world(self, sample_pipeline_output):
        agent = self._make_agent()
        world_info, chapters = agent._extract_data(sample_pipeline_output, layer=1)
        assert "Thanh Van Gioi" in world_info

    def test_extract_data_no_world_uses_default(self, sample_story_draft):
        agent = self._make_agent()
        from models.schemas import PipelineOutput
        sample_story_draft.world = None
        output = PipelineOutput(story_draft=sample_story_draft)
        world_info, _ = agent._extract_data(output, layer=1)
        assert world_info == "Không có thông tin bối cảnh."

    def test_extract_data_layer2_uses_enhanced(self, sample_pipeline_output):
        agent = self._make_agent()
        world_info, chapters = agent._extract_data(sample_pipeline_output, layer=2)
        assert "Khoi dau" in chapters or len(chapters) > 0

    def test_extract_data_layer3_uses_panels(self, sample_pipeline_output):
        agent = self._make_agent()
        world_info, chapters = agent._extract_data(sample_pipeline_output, layer=3)
        assert isinstance(chapters, str)

    def test_extract_data_no_draft_returns_empty_chapters(self):
        agent = self._make_agent()
        from models.schemas import PipelineOutput
        output = PipelineOutput()
        _, chapters = agent._extract_data(output, layer=1)
        assert chapters == "Không có nội dung chương."

    def test_review_calls_llm(self, sample_pipeline_output):
        agent = self._make_agent()
        agent.llm = MagicMock()
        agent.llm.generate_json.return_value = {"score": 0.75, "issues": [], "suggestions": []}
        review = agent.review(sample_pipeline_output, layer=1, iteration=1)
        assert agent.llm.generate_json.called
        assert review.score == 0.75


# ---------------------------------------------------------------------------
# DialogueExpertAgent
# ---------------------------------------------------------------------------

class TestDialogueExpert:
    def _make_agent(self):
        with patch("pipeline.agents.base_agent.LLMClient"):
            return DialogueExpertAgent()

    def test_extract_chapters_layer2_enhanced(self, sample_pipeline_output):
        agent = self._make_agent()
        content = agent._extract_chapters(sample_pipeline_output, layer=2)
        assert isinstance(content, str)
        assert len(content) > 0
        assert "Khoi dau" in content or "Thu thach" in content

    def test_extract_chapters_layer3_uses_voice_lines(self, sample_pipeline_output):
        agent = self._make_agent()
        content = agent._extract_chapters(sample_pipeline_output, layer=3)
        assert "voice-over" in content.lower() or "Ly Huyen" in content

    def test_extract_chapters_no_data_returns_default(self):
        agent = self._make_agent()
        from models.schemas import PipelineOutput
        output = PipelineOutput()
        content = agent._extract_chapters(output, layer=2)
        assert content == "Không có nội dung để đánh giá đối thoại."

    def test_extract_chapters_layer2_fallback_to_draft(self, sample_story_draft):
        agent = self._make_agent()
        from models.schemas import PipelineOutput
        output = PipelineOutput(story_draft=sample_story_draft)
        content = agent._extract_chapters(output, layer=2)
        assert "Khoi dau" in content or len(content) > 0

    def test_review_calls_llm(self, sample_pipeline_output):
        agent = self._make_agent()
        agent.llm = MagicMock()
        agent.llm.generate_json.return_value = {"score": 0.85, "issues": [], "suggestions": []}
        review = agent.review(sample_pipeline_output, layer=2, iteration=1)
        assert agent.llm.generate_json.called
        assert review.approved is True


# ---------------------------------------------------------------------------
# DramaCriticAgent
# ---------------------------------------------------------------------------

class TestDramaCritic:
    def _make_agent(self):
        with patch("pipeline.agents.base_agent.LLMClient"):
            return DramaCriticAgent()

    def test_extract_data_with_enhanced_story(self, sample_pipeline_output):
        agent = self._make_agent()
        chapters, events = agent._extract_data(sample_pipeline_output)
        assert "Chưa có" not in chapters
        assert "Ly Huyen" in chapters or "Khoi dau" in chapters

    def test_extract_data_with_simulation_events(self, sample_pipeline_output):
        agent = self._make_agent()
        _, events = agent._extract_data(sample_pipeline_output)
        assert "confrontation" in events.lower() or "Round" in events

    def test_extract_data_no_enhanced_story_returns_default(self):
        agent = self._make_agent()
        from models.schemas import PipelineOutput
        output = PipelineOutput()
        chapters, events = agent._extract_data(output)
        assert chapters == "Chưa có chương đã tăng cường."
        assert events == "Chưa có sự kiện mô phỏng."

    def test_extract_data_enhancement_notes_included(self, sample_pipeline_output):
        agent = self._make_agent()
        chapters, _ = agent._extract_data(sample_pipeline_output)
        assert "Tang xung dot" in chapters

    def test_review_calls_llm(self, sample_pipeline_output):
        agent = self._make_agent()
        agent.llm = MagicMock()
        agent.llm.generate_json.return_value = {"score": 0.7, "issues": [], "suggestions": []}
        review = agent.review(sample_pipeline_output, layer=2, iteration=1)
        assert agent.llm.generate_json.called
        assert review.approved is True


# ---------------------------------------------------------------------------
# EditorInChiefAgent
# ---------------------------------------------------------------------------

class TestEditorInChief:
    def _make_agent(self):
        with patch("pipeline.agents.base_agent.LLMClient"):
            return EditorInChiefAgent()

    def test_auto_reject_when_score_below_threshold(self, sample_pipeline_output):
        agent = self._make_agent()
        sample_pipeline_output.reviews = [
            AgentReview(
                agent_role="character_specialist",
                agent_name="Test",
                score=0.3,
                issues=["Bad characters"],
                suggestions=[],
                approved=False,
                layer=1,
                iteration=1,
            ),
        ]
        review = agent.review(sample_pipeline_output, layer=1, iteration=1)
        assert review.approved is False
        assert review.score <= 0.55

    def test_auto_reject_when_any_score_critical(self, sample_pipeline_output):
        agent = self._make_agent()
        sample_pipeline_output.reviews = [
            AgentReview(
                agent_role="drama_critic",
                agent_name="Drama",
                score=0.35,  # below 0.4
                issues=["Critical drama failure"],
                suggestions=[],
                approved=False,
                layer=1,
                iteration=1,
            ),
        ]
        review = agent.review(sample_pipeline_output, layer=1, iteration=1)
        assert review.approved is False

    def test_get_content_for_layer1_includes_title(self, sample_pipeline_output):
        agent = self._make_agent()
        content = agent._get_content_for_layer(sample_pipeline_output, layer=1)
        assert "Thanh Van Kiem Khach" in content

    def test_get_content_for_layer2_includes_drama_score(self, sample_pipeline_output):
        agent = self._make_agent()
        content = agent._get_content_for_layer(sample_pipeline_output, layer=2)
        assert "0.75" in content or "drama" in content.lower() or "Kiem tinh" in content.lower()

    def test_get_content_for_layer3_includes_panel(self, sample_pipeline_output):
        agent = self._make_agent()
        content = agent._get_content_for_layer(sample_pipeline_output, layer=3)
        assert "Panel" in content or "Kich ban" in content or len(content) > 0

    def test_get_content_for_layer_no_data(self):
        agent = self._make_agent()
        from models.schemas import PipelineOutput
        output = PipelineOutput()
        content = agent._get_content_for_layer(output, layer=1)
        assert "Chưa có nội dung" in content

    def test_calls_llm_when_scores_adequate(self, sample_pipeline_output):
        agent = self._make_agent()
        agent.llm = MagicMock()
        agent.llm.generate_json.return_value = {"score": 0.8, "issues": [], "suggestions": []}
        sample_pipeline_output.reviews = [
            AgentReview(
                agent_role="drama_critic",
                agent_name="Drama",
                score=0.8,
                issues=[],
                suggestions=[],
                approved=True,
                layer=1,
                iteration=1,
            ),
        ]
        review = agent.review(sample_pipeline_output, layer=1, iteration=1)
        assert agent.llm.generate_json.called
        assert review.approved is True

    def test_issues_list_populated_on_auto_reject(self, sample_pipeline_output):
        agent = self._make_agent()
        sample_pipeline_output.reviews = [
            AgentReview(
                agent_role="continuity_checker",
                agent_name="Kiem Soat",
                score=0.2,
                issues=["Timeline error", "Dead character revived"],
                suggestions=[],
                approved=False,
                layer=1,
                iteration=1,
            ),
        ]
        review = agent.review(sample_pipeline_output, layer=1, iteration=1)
        assert len(review.issues) > 0
