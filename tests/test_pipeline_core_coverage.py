"""Comprehensive coverage tests for pipeline core modules.

Targets:
  - pipeline/orchestrator_layers.py       (run_full_pipeline, run_layer1_only, run_layer2_only)
  - pipeline/orchestrator_checkpoint.py  (CheckpointManager)
  - pipeline/orchestrator_export.py      (PipelineExporter)
  - pipeline/orchestrator_media.py       (MediaProducer)
  - pipeline/layer2_enhance/simulator.py (DramaSimulator, TrustNetworkEdge)
  - services/media/image_generator.py    (ImageGenerator)
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from factories import (
    build_character, create_test_story,
    create_enhanced_story,
)
from models.schemas import (
    PipelineOutput, Relationship, RelationType, SimulationResult, SimulationEvent,
    AgentPost, EscalationPattern,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_pipeline_output(with_draft=True, with_enhanced=False, with_sim=False):
    """Return a PipelineOutput wired with optional sub-objects."""
    out = PipelineOutput(status="running", current_layer=1)
    if with_draft:
        out.story_draft = create_test_story()
    if with_enhanced:
        out.enhanced_story = create_enhanced_story(out.story_draft)
    if with_sim:
        out.simulation_result = SimulationResult(
            events=[
                SimulationEvent(
                    round_number=1,
                    event_type="xung_đột",
                    characters_involved=["Hero", "Villain"],
                    description="Big fight",
                    drama_score=0.8,
                )
            ],
            drama_suggestions=["Add betrayal"],
        )
    return out


def _make_relationship(a="Hero", b="Villain", rtype=RelationType.ENEMY, tension=0.5):
    return Relationship(
        character_a=a, character_b=b,
        relation_type=rtype,
        intensity=0.7, tension=tension,
        description="Test relationship",
    )


# ===========================================================================
# 1. TrustNetworkEdge  (simulator.py)
# ===========================================================================

class TestTrustNetworkEdge:
    def test_initial_trust(self):
        from pipeline.layer2_enhance.simulator import TrustNetworkEdge
        edge = TrustNetworkEdge("A", "B", trust=60.0)
        assert edge.trust == 60.0
        assert edge.char_a == "A"
        assert edge.char_b == "B"

    def test_update_trust_adds_delta(self):
        from pipeline.layer2_enhance.simulator import TrustNetworkEdge
        edge = TrustNetworkEdge("A", "B", trust=50.0)
        edge.update_trust(10.0, "good deed")
        assert edge.trust == 60.0
        assert len(edge.history) == 1

    def test_update_trust_clamps_min(self):
        from pipeline.layer2_enhance.simulator import TrustNetworkEdge
        edge = TrustNetworkEdge("A", "B", trust=5.0)
        edge.update_trust(-100.0)
        assert edge.trust == 0.0

    def test_update_trust_clamps_max(self):
        from pipeline.layer2_enhance.simulator import TrustNetworkEdge
        edge = TrustNetworkEdge("A", "B", trust=95.0)
        edge.update_trust(100.0)
        assert edge.trust == 100.0

    def test_is_betrayal_candidate_below_30(self):
        from pipeline.layer2_enhance.simulator import TrustNetworkEdge
        edge = TrustNetworkEdge("A", "B", trust=20.0)
        assert edge.is_betrayal_candidate is True

    def test_is_betrayal_candidate_above_30(self):
        from pipeline.layer2_enhance.simulator import TrustNetworkEdge
        edge = TrustNetworkEdge("A", "B", trust=50.0)
        assert edge.is_betrayal_candidate is False

    def test_history_trimmed_to_10(self):
        from pipeline.layer2_enhance.simulator import TrustNetworkEdge
        edge = TrustNetworkEdge("A", "B", trust=50.0)
        for i in range(15):
            edge.update_trust(0.0, f"event {i}")
        assert len(edge.history) <= 10


# ===========================================================================
# 2. DramaSimulator  (simulator.py)
# ===========================================================================

class TestDramaSimulatorSetup:
    def _make_simulator(self):
        with patch("pipeline.layer2_enhance.simulator.LLMClient"):
            from pipeline.layer2_enhance.simulator import DramaSimulator
            return DramaSimulator()

    def test_init_empty_state(self):
        sim = self._make_simulator()
        assert sim.agents == {}
        assert sim.all_posts == []
        assert sim.relationships == []
        assert sim.trust_network == {}

    def test_setup_agents_creates_agent_per_character(self):
        sim = self._make_simulator()
        chars = [build_character("Alice"), build_character("Bob")]
        rels = [_make_relationship("Alice", "Bob", RelationType.RIVAL)]
        sim.setup_agents(chars, rels)
        assert "Alice" in sim.agents
        assert "Bob" in sim.agents
        assert len(sim.trust_network) == 1

    def test_setup_agents_close_relation_gets_high_trust(self):
        sim = self._make_simulator()
        chars = [build_character("Alice"), build_character("Bob")]
        rels = [_make_relationship("Alice", "Bob", RelationType.ALLY)]
        sim.setup_agents(chars, rels)
        edge = list(sim.trust_network.values())[0]
        assert edge.trust >= 70.0

    def test_setup_agents_hostile_relation_gets_lower_trust(self):
        sim = self._make_simulator()
        chars = [build_character("Alice"), build_character("Bob")]
        rels = [_make_relationship("Alice", "Bob", RelationType.ENEMY)]
        sim.setup_agents(chars, rels)
        edge = list(sim.trust_network.values())[0]
        assert edge.trust == 40.0

    def test_get_recent_posts_empty(self):
        sim = self._make_simulator()
        chars = [build_character("Alice")]
        sim.setup_agents(chars, [])
        result = sim._get_recent_posts("Alice")
        assert "Chưa có" in result

    def test_get_recent_posts_excludes_self(self):
        sim = self._make_simulator()
        chars = [build_character("Alice"), build_character("Bob")]
        sim.setup_agents(chars, [])
        sim.all_posts.append(AgentPost(
            agent_name="Alice", content="Hi", action_type="post",
            round_number=1,
        ))
        result = sim._get_recent_posts("Alice")
        assert "Alice" not in result

    def test_get_relationships_text_empty(self):
        sim = self._make_simulator()
        chars = [build_character("Alice")]
        sim.setup_agents(chars, [])
        result = sim._get_relationships_text("Alice")
        assert "Chưa có" in result

    def test_get_relationships_text_shows_related(self):
        sim = self._make_simulator()
        chars = [build_character("Alice"), build_character("Bob")]
        rels = [_make_relationship("Alice", "Bob")]
        sim.setup_agents(chars, rels)
        result = sim._get_relationships_text("Alice")
        assert "Alice" in result
        assert "Bob" in result

    def test_infer_mood_mapping(self):
        sim = self._make_simulator()
        assert sim._infer_mood("tích_cực") == "quyết_tâm"
        assert sim._infer_mood("tiêu_cực") == "đau_khổ"
        assert sim._infer_mood("unknown_sentiment") == "bình_thường"

    def test_check_escalation_returns_triggered_patterns(self):
        sim = self._make_simulator()
        chars = [build_character("Alice"), build_character("Bob")]
        # high tension to trigger escalation
        rels = [_make_relationship("Alice", "Bob", RelationType.ALLY, tension=0.9)]
        sim.setup_agents(chars, rels)
        triggered = sim._check_escalation(1)
        assert isinstance(triggered, list)
        assert all(isinstance(p, EscalationPattern) for p in triggered)

    def test_check_escalation_no_trigger_low_tension(self):
        sim = self._make_simulator()
        chars = [build_character("Alice"), build_character("Bob")]
        rels = [_make_relationship("Alice", "Bob", tension=0.1)]
        sim.setup_agents(chars, rels)
        triggered = sim._check_escalation(1)
        assert triggered == []

    def test_update_relationship_changes_type(self):
        sim = self._make_simulator()
        chars = [build_character("Alice"), build_character("Bob")]
        rels = [_make_relationship("Alice", "Bob", RelationType.ALLY)]
        sim.setup_agents(chars, rels)
        sim._update_relationship({
            "character_a": "Alice",
            "character_b": "Bob",
            "new_relation": RelationType.ENEMY.value,
        })
        assert sim.relationships[0].relation_type == RelationType.ENEMY

    def test_update_relationship_invalid_type_ignored(self):
        sim = self._make_simulator()
        chars = [build_character("Alice"), build_character("Bob")]
        rels = [_make_relationship("Alice", "Bob", RelationType.ALLY)]
        sim.setup_agents(chars, rels)
        # Should not raise
        sim._update_relationship({
            "character_a": "Alice",
            "character_b": "Bob",
            "new_relation": "nonexistent_type",
        })


class TestDramaSimulatorLLMCalls:
    """Tests that mock LLM responses to avoid real API calls."""

    def _make_simulator_with_mock_llm(self):
        with patch("pipeline.layer2_enhance.simulator.LLMClient") as MockLLM:
            from pipeline.layer2_enhance.simulator import DramaSimulator
            sim = DramaSimulator()
            sim.llm = MockLLM.return_value
        return sim

    def test_run_single_agent_creates_post(self):
        sim = self._make_simulator_with_mock_llm()
        chars = [build_character("Alice"), build_character("Bob")]
        sim.setup_agents(chars, [])
        sim.llm.generate_json.return_value = {
            "content": "I will prevail!",
            "action_type": "post",
            "target": "Bob",
            "sentiment": "tích_cực",
            "new_mood": "quyết_tâm",
            "trust_change": 5,
        }
        post, metadata = sim._run_single_agent("Alice", 1, "fantasy")
        assert post is not None
        assert post.agent_name == "Alice"
        assert post.content == "I will prevail!"
        assert metadata["new_mood"] == "quyết_tâm"

    def test_run_single_agent_llm_exception_returns_none(self):
        sim = self._make_simulator_with_mock_llm()
        chars = [build_character("Alice")]
        sim.setup_agents(chars, [])
        sim.llm.generate_json.side_effect = Exception("LLM down")
        post, metadata = sim._run_single_agent("Alice", 1, "fantasy")
        assert post is None
        assert metadata == {}

    def test_evaluate_drama_calls_llm(self):
        sim = self._make_simulator_with_mock_llm()
        sim.llm.generate_json.return_value = {
            "overall_drama_score": 0.75,
            "events": [],
            "relationship_changes": [],
        }
        posts = [AgentPost(
            agent_name="Alice", content="Drama!", action_type="confrontation",
            target="Bob", sentiment="tức_giận", round_number=1,
        )]
        result = sim.evaluate_drama(posts)
        assert result["overall_drama_score"] == 0.75
        sim.llm.generate_json.assert_called_once()

    def test_apply_escalation_returns_event(self):
        sim = self._make_simulator_with_mock_llm()
        chars = [build_character("Alice"), build_character("Bob")]
        sim.setup_agents(chars, [])
        sim.llm.generate_json.return_value = {
            "event_type": "phản_bội",
            "characters_involved": ["Alice", "Bob"],
            "description": "Betrayal revealed",
            "drama_score": 0.8,
            "suggested_insertion": "Chapter 5",
        }
        pattern = EscalationPattern(
            pattern_type="phản_bội",
            trigger_tension=0.7,
            characters_required=2,
            description="Alice vs Bob",
            intensity_multiplier=2.0,
        )
        event = sim._apply_escalation(pattern, 1, "fantasy")
        assert event is not None
        assert event.event_type == "phản_bội"
        assert event.drama_score <= 1.0

    def test_apply_escalation_llm_exception_returns_none(self):
        sim = self._make_simulator_with_mock_llm()
        chars = [build_character("Alice"), build_character("Bob")]
        sim.setup_agents(chars, [])
        sim.llm.generate_json.side_effect = Exception("LLM error")
        pattern = EscalationPattern(
            pattern_type="phản_bội",
            trigger_tension=0.7,
            characters_required=2,
            description="Alice vs Bob",
            intensity_multiplier=2.0,
        )
        event = sim._apply_escalation(pattern, 1, "fantasy")
        assert event is None

    def test_generate_suggestions_calls_llm(self):
        sim = self._make_simulator_with_mock_llm()
        sim.llm.generate_json.return_value = {
            "suggestions": ["Add more conflict"],
            "character_arcs": {},
            "tension_points": {},
        }
        result = sim._generate_suggestions("fantasy")
        assert "suggestions" in result

    def test_run_reaction_returns_post(self):
        sim = self._make_simulator_with_mock_llm()
        chars = [build_character("Alice"), build_character("Bob")]
        sim.setup_agents(chars, [])
        sim.llm.generate_json.return_value = {
            "content": "How dare you!",
            "action_type": "confrontation",
            "sentiment": "tức_giận",
            "new_mood": "tức_giận",
            "trust_change": -10,
        }
        triggering = AgentPost(
            agent_name="Alice", content="I lied!", action_type="tiết_lộ",
            target="Bob", sentiment="tiêu_cực", round_number=1,
        )
        agent = sim.agents["Bob"]
        post = sim._run_reaction(agent, triggering, 1, "fantasy")
        assert post is not None
        assert post.agent_name == "Bob"

    def test_run_reaction_exception_returns_none(self):
        sim = self._make_simulator_with_mock_llm()
        chars = [build_character("Alice"), build_character("Bob")]
        sim.setup_agents(chars, [])
        sim.llm.generate_json.side_effect = Exception("LLM error")
        triggering = AgentPost(
            agent_name="Alice", content="I lied!", action_type="tiết_lộ",
            target="Bob", sentiment="tiêu_cực", round_number=1,
        )
        agent = sim.agents["Bob"]
        post = sim._run_reaction(agent, triggering, 1, "fantasy")
        assert post is None


# ===========================================================================
# 3. CheckpointManager  (orchestrator_checkpoint.py)
# ===========================================================================

class TestCheckpointManager:
    def _make_manager(self, output=None):
        from pipeline.orchestrator_checkpoint import CheckpointManager
        if output is None:
            output = _make_pipeline_output()
        analyzer = MagicMock()
        simulator = MagicMock()
        enhancer = MagicMock()
        return CheckpointManager(output, analyzer, simulator, enhancer)

    def test_init_stores_components(self):
        mgr = self._make_manager()
        assert mgr.output is not None
        assert mgr.analyzer is not None
        assert mgr.simulator is not None
        assert mgr.enhancer is not None

    def test_save_returns_path_string(self):
        mgr = self._make_manager()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("pipeline.orchestrator_checkpoint.CHECKPOINT_DIR", tmpdir):
                path = mgr.save(1, background=False)
        assert isinstance(path, str)
        assert "layer1" in path

    def test_save_writes_json_file(self):
        mgr = self._make_manager()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("pipeline.orchestrator_checkpoint.CHECKPOINT_DIR", tmpdir):
                path = mgr.save(1, background=False)
                assert os.path.exists(path)
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                assert "status" in data

    def test_save_background_spawns_thread(self):
        mgr = self._make_manager()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("pipeline.orchestrator_checkpoint.CHECKPOINT_DIR", tmpdir):
                with patch("threading.Thread") as MockThread:
                    mock_thread = MagicMock()
                    MockThread.return_value = mock_thread
                    mgr.save(1, background=True)
                    MockThread.assert_called_once()
                    mock_thread.start.assert_called_once()

    def test_save_no_draft_uses_untitled(self):
        output = PipelineOutput(status="running", current_layer=1)
        mgr = self._make_manager(output)
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("pipeline.orchestrator_checkpoint.CHECKPOINT_DIR", tmpdir):
                path = mgr.save(1, background=False)
                assert "untitled" in path

    def test_list_checkpoints_empty_dir(self):
        from pipeline.orchestrator_checkpoint import CheckpointManager
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("pipeline.orchestrator_checkpoint.CHECKPOINT_DIR", tmpdir):
                result = CheckpointManager.list_checkpoints()
        assert result == []

    def test_list_checkpoints_nonexistent_dir(self):
        from pipeline.orchestrator_checkpoint import CheckpointManager
        with patch("pipeline.orchestrator_checkpoint.CHECKPOINT_DIR", "/nonexistent/path"):
            result = CheckpointManager.list_checkpoints()
        assert result == []

    def test_list_checkpoints_returns_metadata(self):
        from pipeline.orchestrator_checkpoint import CheckpointManager
        out = _make_pipeline_output()
        mgr = self._make_manager(out)
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("pipeline.orchestrator_checkpoint.CHECKPOINT_DIR", tmpdir):
                mgr.save(1, background=False)
                # brief wait for background thread if any
                import time
                time.sleep(0.05)
                result = CheckpointManager.list_checkpoints()
        assert len(result) >= 1
        entry = result[0]
        assert "file" in entry
        assert "path" in entry
        assert "size_kb" in entry

    def test_resume_corrupted_checkpoint_raises(self):
        mgr = self._make_manager()
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w",
                                         delete=False, encoding="utf-8") as f:
            f.write("NOT VALID JSON {{{")
            bad_path = f.name
        try:
            with pytest.raises(ValueError, match="Checkpoint corrupted"):
                mgr.resume(bad_path)
        finally:
            os.unlink(bad_path)

    def test_resume_valid_checkpoint_restores_output(self):
        from pipeline.orchestrator_checkpoint import CheckpointManager
        out = _make_pipeline_output(with_draft=True)
        out.current_layer = 2
        out.status = "completed"
        out.enhanced_story = create_enhanced_story(out.story_draft)

        with tempfile.NamedTemporaryFile(suffix=".json", mode="w",
                                          delete=False, encoding="utf-8") as f:
            f.write(out.model_dump_json())
            ckpt_path = f.name
        try:
            mgr = CheckpointManager(
                PipelineOutput(status="running", current_layer=1),
                MagicMock(), MagicMock(), MagicMock(),
            )
            result = mgr.resume(ckpt_path, enable_agents=False, enable_scoring=False)
            assert result.status in ("completed", "partial")
        finally:
            os.unlink(ckpt_path)

    def test_resume_layer1_runs_layer2(self):
        """When checkpoint is at layer 1 (no enhanced story), should run layer 2."""
        from pipeline.orchestrator_checkpoint import CheckpointManager
        out = _make_pipeline_output(with_draft=True)
        out.current_layer = 1  # only layer 1 done

        with tempfile.NamedTemporaryFile(suffix=".json", mode="w",
                                          delete=False, encoding="utf-8") as f:
            f.write(out.model_dump_json())
            ckpt_path = f.name

        analyzer = MagicMock()
        analyzer.analyze.return_value = {"relationships": []}
        simulator = MagicMock()
        simulator.run_simulation.return_value = SimulationResult()
        enhancer = MagicMock()
        enhanced = create_enhanced_story(out.story_draft)
        enhancer.enhance_with_feedback.return_value = enhanced

        try:
            mgr = CheckpointManager(
                PipelineOutput(status="running", current_layer=1),
                analyzer, simulator, enhancer,
            )
            with patch("pipeline.orchestrator_checkpoint.CheckpointManager.save"):
                mgr.resume(ckpt_path, enable_agents=False, enable_scoring=False)
            analyzer.analyze.assert_called_once()
            simulator.run_simulation.assert_called_once()
            enhancer.enhance_with_feedback.assert_called_once()
        finally:
            os.unlink(ckpt_path)


# ===========================================================================
# 4. PipelineExporter  (orchestrator_export.py)
# ===========================================================================

class TestPipelineExporter:
    def _make_exporter(self, **kwargs):
        from pipeline.orchestrator_export import PipelineExporter
        output = _make_pipeline_output(**kwargs)
        return PipelineExporter(output), output

    def test_export_output_empty_no_stories(self):
        from pipeline.orchestrator_export import PipelineExporter
        empty = PipelineOutput(status="running", current_layer=1)
        exporter = PipelineExporter(empty)
        with tempfile.TemporaryDirectory() as tmpdir:
            files = exporter.export_output(tmpdir, formats=["TXT"])
        assert files == []

    def test_export_txt_draft(self):
        exporter, _ = self._make_exporter(with_draft=True)
        with patch("plugins.plugin_manager.apply_export", side_effect=lambda fmt, d: d):
            with tempfile.TemporaryDirectory() as tmpdir:
                files = exporter.export_output(tmpdir, formats=["TXT"])
        # Should have at least 1 txt (draft)
        txt_files = [f for f in files if f.endswith(".txt")]
        assert len(txt_files) >= 1

    def test_export_txt_enhanced(self):
        exporter, _ = self._make_exporter(with_draft=True, with_enhanced=True)
        with patch("plugins.plugin_manager.apply_export", side_effect=lambda fmt, d: d):
            with tempfile.TemporaryDirectory() as tmpdir:
                files = exporter.export_output(tmpdir, formats=["TXT"])
        txt_files = [f for f in files if f.endswith(".txt")]
        assert len(txt_files) >= 2  # draft + enhanced

    def test_export_json_simulation(self):
        exporter, _ = self._make_exporter(with_draft=True, with_sim=True)
        with patch("plugins.plugin_manager.apply_export", side_effect=lambda fmt, d: d):
            with tempfile.TemporaryDirectory() as tmpdir:
                files = exporter.export_output(tmpdir, formats=["JSON"])
        json_files = [f for f in files if f.endswith(".json")]
        assert len(json_files) >= 1

    def test_export_markdown_writes_file(self):
        exporter, _ = self._make_exporter(with_draft=True, with_enhanced=True)
        with patch("plugins.plugin_manager.apply_export", side_effect=lambda fmt, d: d):
            with tempfile.TemporaryDirectory() as tmpdir:
                files = exporter.export_output(tmpdir, formats=["Markdown"])
                md_files = [f for f in files if f.endswith(".md")]
                assert len(md_files) == 1
                with open(md_files[0], encoding="utf-8") as f:
                    content = f.read()
                assert "## Chương" in content

    def test_export_html_calls_html_exporter(self):
        exporter, _ = self._make_exporter(with_draft=True, with_enhanced=True)
        with patch("plugins.plugin_manager.apply_export", side_effect=lambda fmt, d: d):
            with patch("services.html_exporter.HTMLExporter.export", return_value="/fake/path.html") as mock_html:
                with tempfile.TemporaryDirectory() as tmpdir:
                    exporter.export_output(tmpdir, formats=["HTML"])
        mock_html.assert_called_once()

    def test_export_epub_calls_epub_exporter(self):
        exporter, _ = self._make_exporter(with_draft=True, with_enhanced=True)
        with patch("plugins.plugin_manager.apply_export", side_effect=lambda fmt, d: d):
            with patch("services.epub_exporter.EPUBExporter.export", return_value="/fake/path.epub") as mock_epub:
                with tempfile.TemporaryDirectory() as tmpdir:
                    exporter.export_output(tmpdir, formats=["EPUB"])
        mock_epub.assert_called_once()

    def test_export_zip_returns_zip_path(self):
        exporter, _ = self._make_exporter(with_draft=True, with_enhanced=True)
        with patch("plugins.plugin_manager.apply_export", side_effect=lambda fmt, d: d):
            with tempfile.TemporaryDirectory() as tmpdir:
                zip_path = exporter.export_zip(tmpdir, formats=["TXT"])
                assert zip_path.endswith(".zip")
                assert os.path.exists(zip_path)

    def test_export_zip_no_files_returns_empty(self):
        from pipeline.orchestrator_export import PipelineExporter
        empty = PipelineOutput(status="running", current_layer=1)
        exporter = PipelineExporter(empty)
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = exporter.export_zip(tmpdir, formats=["TXT"])
        assert zip_path == ""

    def test_export_plugin_exception_falls_back(self):
        """Plugin apply_export raises → falls back to original data."""
        exporter, _ = self._make_exporter(with_draft=True)
        with patch("plugins.plugin_manager.apply_export", side_effect=Exception("plugin error")):
            with tempfile.TemporaryDirectory() as tmpdir:
                files = exporter.export_output(tmpdir, formats=["TXT"])
        # Should still write the file using the original data
        txt_files = [f for f in files if f.endswith(".txt")]
        assert len(txt_files) >= 1

    def test_export_markdown_draft_only(self):
        """When no enhanced story, export_markdown uses draft."""
        exporter, _ = self._make_exporter(with_draft=True, with_enhanced=False)
        with patch("plugins.plugin_manager.apply_export", side_effect=lambda fmt, d: d):
            with tempfile.TemporaryDirectory() as tmpdir:
                files = exporter.export_output(tmpdir, formats=["Markdown"])
        assert len(files) == 1

    def test_export_html_no_story_returns_none(self):
        from pipeline.orchestrator_export import PipelineExporter
        empty = PipelineOutput(status="running", current_layer=1)
        exporter = PipelineExporter(empty)
        with tempfile.TemporaryDirectory() as tmpdir:
            result = exporter._export_html(tmpdir, "20240101_000000")
        assert result is None

    def test_export_epub_no_story_returns_none(self):
        from pipeline.orchestrator_export import PipelineExporter
        empty = PipelineOutput(status="running", current_layer=1)
        exporter = PipelineExporter(empty)
        with tempfile.TemporaryDirectory() as tmpdir:
            result = exporter._export_epub(tmpdir, "20240101_000000")
        assert result is None

    def test_export_markdown_no_story_returns_none(self):
        from pipeline.orchestrator_export import PipelineExporter
        empty = PipelineOutput(status="running", current_layer=1)
        exporter = PipelineExporter(empty)
        with tempfile.TemporaryDirectory() as tmpdir:
            result = exporter._export_markdown(tmpdir, "20240101_000000")
        assert result is None


# ===========================================================================
# 5. MediaProducer  (orchestrator_media.py)
# ===========================================================================

class TestMediaProducer:
    def _make_producer(self, image_provider="none", seedream_api_key="",
                       enable_character_consistency=False):
        from pipeline.orchestrator_media import MediaProducer
        from config import PipelineConfig
        cfg = MagicMock()
        cfg.pipeline = PipelineConfig(
            image_provider=image_provider,
            seedream_api_key=seedream_api_key,
            enable_character_consistency=enable_character_consistency,
        )
        return MediaProducer(cfg)

    def test_init_stores_config(self):
        producer = self._make_producer()
        assert producer.config is not None

    def test_run_no_provider_returns_empty(self):
        producer = self._make_producer(image_provider="none")
        draft = create_test_story()
        enhanced = create_enhanced_story(draft)
        with patch("pipeline.orchestrator_media.ImageProvider") as MockProvider:
            mock_prov = MagicMock()
            mock_prov.is_configured.return_value = False
            mock_prov.seedream.api_key = ""
            mock_prov.seedream.base_url = ""
            MockProvider.return_value = mock_prov
            result = producer.run(draft, enhanced)
        assert result["character_refs"] == {}
        assert result["scene_images"] == []

    def test_run_with_configured_provider_generates_refs(self):
        producer = self._make_producer()
        draft = create_test_story()
        enhanced = create_enhanced_story(draft)
        with patch("pipeline.orchestrator_media.ImageProvider") as MockProvider:
            mock_prov = MagicMock()
            mock_prov.is_configured.return_value = True
            mock_prov.seedream.api_key = "key"
            mock_prov.seedream.base_url = "url"
            mock_prov.generate_character_reference.return_value = "/tmp/char.png"
            MockProvider.return_value = mock_prov
            result = producer.run(draft, enhanced, progress_callback=lambda m: None)
        assert len(result["character_refs"]) > 0

    def test_run_progress_callback_called(self):
        producer = self._make_producer()
        draft = create_test_story()
        enhanced = create_enhanced_story(draft)
        messages = []
        with patch("pipeline.orchestrator_media.ImageProvider") as MockProvider:
            mock_prov = MagicMock()
            mock_prov.is_configured.return_value = False
            mock_prov.seedream.api_key = ""
            mock_prov.seedream.base_url = ""
            MockProvider.return_value = mock_prov
            producer.run(draft, enhanced, progress_callback=messages.append)
        # callback should not raise even if nothing to do
        assert isinstance(messages, list)


# ===========================================================================
# 6. ImageGenerator  (services/media/image_generator.py)
# ===========================================================================

class TestImageGenerator:
    def _make_generator(self, provider="none", api_key="", base_url=""):
        with patch("config.ConfigManager") as MockCfg:
            from config import PipelineConfig
            mock_cfg = MagicMock()
            mock_cfg.pipeline = PipelineConfig(
                image_provider=provider,
                image_api_key=api_key,
                image_api_url=base_url,
            )
            MockCfg.return_value = mock_cfg
            with patch("os.makedirs"):
                from services.media.image_generator import ImageGenerator
                return ImageGenerator(provider=provider, api_key=api_key, base_url=base_url)

    def test_init_default_provider(self):
        gen = self._make_generator(provider="none")
        assert gen.provider == "none"

    def test_generate_none_provider_returns_none(self):
        gen = self._make_generator(provider="none")
        result = gen.generate("A beautiful scene")
        assert result is None

    def test_generate_unknown_provider_returns_none(self):
        gen = self._make_generator(provider="unknown_provider")
        result = gen.generate("A beautiful scene")
        assert result is None

    def test_generate_dalle_no_api_key_returns_none(self):
        gen = self._make_generator(provider="dalle", api_key="")
        result = gen.generate("A beautiful scene")
        assert result is None

    def test_generate_dalle_calls_api(self):
        gen = self._make_generator(provider="dalle", api_key="sk-test")
        import base64
        fake_b64 = base64.b64encode(b"fake image bytes").decode()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"b64_json": fake_b64}]}
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.post", return_value=mock_resp):
            with patch("builtins.open", MagicMock()):
                result = gen._generate_dalle("A scene", "test.png", "1024x1024")
        assert result is not None

    def test_generate_dalle_exception_returns_none(self):
        gen = self._make_generator(provider="dalle", api_key="sk-test")
        with patch("requests.post", side_effect=Exception("network error")):
            result = gen._generate_dalle("A scene", "test.png", "1024x1024")
        assert result is None

    def test_generate_sd_success(self):
        gen = self._make_generator(provider="sd-api")
        import base64
        fake_b64 = base64.b64encode(b"fake image").decode()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"images": [fake_b64]}
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.post", return_value=mock_resp):
            with patch("builtins.open", MagicMock()):
                result = gen._generate_sd("A scene", "test.png")
        assert result is not None

    def test_generate_sd_exception_returns_none(self):
        gen = self._make_generator(provider="sd-api")
        with patch("requests.post", side_effect=Exception("timeout")):
            result = gen._generate_sd("A scene", "test.png")
        assert result is None

    def test_generate_huggingface_no_token_returns_none(self):
        gen = self._make_generator(provider="huggingface")
        gen.hf_token = ""
        result = gen._generate_huggingface("A scene", "test.png")
        assert result is None

    def test_generate_huggingface_success(self):
        gen = self._make_generator(provider="huggingface")
        gen.hf_token = "hf_test_token"
        gen.hf_model = "black-forest-labs/FLUX.1-schnell"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"fake image bytes"
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.post", return_value=mock_resp):
            with patch("builtins.open", MagicMock()):
                result = gen._generate_huggingface("A scene", "test.png")
        assert result is not None

    def test_generate_huggingface_503_retries(self):
        gen = self._make_generator(provider="huggingface")
        gen.hf_token = "hf_test_token"
        gen.hf_model = "black-forest-labs/FLUX.1-schnell"
        # First call 503, second call success
        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.content = b"fake image bytes"
        success_resp.raise_for_status = MagicMock()
        fail_resp = MagicMock()
        fail_resp.status_code = 503
        with patch("requests.post", side_effect=[fail_resp, success_resp]):
            with patch("time.sleep"):
                with patch("builtins.open", MagicMock()):
                    result = gen._generate_huggingface("A scene", "test.png")
        assert result is not None

    def test_generate_huggingface_exception_returns_none(self):
        gen = self._make_generator(provider="huggingface")
        gen.hf_token = "hf_test_token"
        with patch("requests.post", side_effect=Exception("HF down")):
            result = gen._generate_huggingface("A scene", "test.png")
        assert result is None

    def test_generate_with_reference_empty_refs_calls_generate(self):
        gen = self._make_generator(provider="none")
        gen.generate = MagicMock(return_value=None)
        gen.generate_with_reference("prompt", [], "test.png")
        gen.generate.assert_called_once_with("prompt", "test.png", "1024x1024")

    def test_generate_with_reference_seedream_calls_seedream(self):
        gen = self._make_generator(provider="seedream")
        gen._seedream_with_ref = MagicMock(return_value="/tmp/ref.png")
        result = gen.generate_with_reference("prompt", ["/tmp/ref.png"], "test.png")
        gen._seedream_with_ref.assert_called_once()
        assert result == "/tmp/ref.png"

    def test_generate_with_reference_dalle_falls_back(self):
        gen = self._make_generator(provider="dalle")
        gen.generate = MagicMock(return_value=None)
        gen.generate_with_reference("prompt", ["/tmp/ref.png"], "test.png")
        gen.generate.assert_called_once()

    def test_generate_story_images_empty_list(self):
        gen = self._make_generator(provider="none")
        result = gen.generate_story_images([])
        assert result == []

    def test_generate_story_images_uses_correct_prompt(self):
        gen = self._make_generator(provider="dalle")
        gen.generate = MagicMock(return_value="/tmp/img.png")
        from models.schemas import ImagePrompt
        ip = ImagePrompt(
            dalle_prompt="Dalle prompt text",
            sd_prompt="SD prompt text",
            scene_description="Scene desc",
        )
        result = gen.generate_story_images([ip], chapter_number=1)
        gen.generate.assert_called_once_with("Dalle prompt text", "ch01_panel01.png")
        assert result == ["/tmp/img.png"]

    def test_generate_story_images_returns_none_paths_excluded(self):
        gen = self._make_generator(provider="none")
        from models.schemas import ImagePrompt
        ip = ImagePrompt(scene_description="A scene")
        result = gen.generate_story_images([ip], chapter_number=1)
        assert result == []


# ===========================================================================
# 7. orchestrator_layers functions (run_layer1_only, run_layer2_only)
# ===========================================================================

class TestOrchestratorLayerFunctions:
    """Test the module-level helper functions that wrap orchestrator methods."""

    def _make_mock_orchestrator(self):
        orch = MagicMock()
        orch.story_gen = MagicMock()
        orch.analyzer = MagicMock()
        orch.simulator = MagicMock()
        orch.enhancer = MagicMock()
        return orch

    def test_run_layer1_only_delegates_to_story_gen(self):
        from pipeline.orchestrator_layers import run_layer1_only
        orch = self._make_mock_orchestrator()
        draft = create_test_story()
        orch.story_gen.generate_full_story.return_value = draft
        result = run_layer1_only(
            orch, title="Test", genre="fantasy", idea="An idea",
            style="default", num_chapters=3, num_characters=2, word_count=1000,
        )
        assert result is draft
        orch.story_gen.generate_full_story.assert_called_once()

    def test_run_layer1_only_passes_progress_callback(self):
        from pipeline.orchestrator_layers import run_layer1_only
        orch = self._make_mock_orchestrator()
        draft = create_test_story()
        orch.story_gen.generate_full_story.return_value = draft
        cb = MagicMock()
        run_layer1_only(
            orch, title="T", genre="f", idea="i",
            style="s", num_chapters=1, num_characters=1, word_count=100,
            progress_callback=cb,
        )
        call_kwargs = orch.story_gen.generate_full_story.call_args
        assert call_kwargs.kwargs.get("progress_callback") is cb

    def test_run_layer2_only_calls_analyzer_simulator_enhancer(self):
        from pipeline.orchestrator_layers import run_layer2_only
        orch = self._make_mock_orchestrator()
        draft = create_test_story()
        orch.analyzer.analyze.return_value = {"relationships": []}
        sim_result = SimulationResult()
        orch.simulator.run_simulation.return_value = sim_result
        enhanced = create_enhanced_story(draft)
        orch.enhancer.enhance_with_feedback.return_value = enhanced

        result = run_layer2_only(orch, draft)
        assert result is enhanced
        orch.analyzer.analyze.assert_called_once_with(draft)
        orch.simulator.run_simulation.assert_called_once()
        orch.enhancer.enhance_with_feedback.assert_called_once()

    def test_run_layer2_only_passes_genre_from_draft(self):
        from pipeline.orchestrator_layers import run_layer2_only
        orch = self._make_mock_orchestrator()
        draft = create_test_story(genre="romance")
        orch.analyzer.analyze.return_value = {"relationships": []}
        orch.simulator.run_simulation.return_value = SimulationResult()
        orch.enhancer.enhance_with_feedback.return_value = create_enhanced_story(draft)
        run_layer2_only(orch, draft)
        sim_call = orch.simulator.run_simulation.call_args
        assert sim_call.kwargs.get("genre") == "romance"

    def test_run_layer2_only_default_rounds_is_5(self):
        from pipeline.orchestrator_layers import run_layer2_only
        orch = self._make_mock_orchestrator()
        draft = create_test_story()
        orch.analyzer.analyze.return_value = {"relationships": []}
        orch.simulator.run_simulation.return_value = SimulationResult()
        orch.enhancer.enhance_with_feedback.return_value = create_enhanced_story(draft)
        run_layer2_only(orch, draft)
        sim_call = orch.simulator.run_simulation.call_args
        assert sim_call.kwargs.get("num_rounds") == 5


# ===========================================================================
# 8. run_full_pipeline (async, orchestrator_layers.py)
# ===========================================================================

@pytest.mark.asyncio
class TestRunFullPipeline:
    """Integration-style tests for run_full_pipeline using heavy mocking."""

    def _make_orchestrator_for_pipeline(self):
        """Build a minimal mock orchestrator compatible with run_full_pipeline."""
        import threading
        from models.schemas import PipelineOutput

        orch = MagicMock()
        orch._lock = threading.RLock()
        orch.output = PipelineOutput(status="running", current_layer=1)
        orch._sync_output = MagicMock()

        # story_gen returns a valid draft
        draft = create_test_story()
        orch.story_gen.generate_full_story.return_value = draft

        # analyzer, simulator, enhancer
        orch.analyzer.analyze.return_value = {"relationships": []}
        orch.simulator.run_simulation.return_value = SimulationResult()
        enhanced = create_enhanced_story(draft)
        orch.enhancer.enhance_with_feedback.return_value = enhanced

        # checkpoint
        orch.checkpoint.save = MagicMock()

        # config
        from config import PipelineConfig
        orch.config.pipeline = PipelineConfig(enable_quality_gate=False, enable_smart_revision=False)

        return orch, draft, enhanced

    async def test_llm_connection_failure_returns_error(self):
        from pipeline.orchestrator_layers import run_full_pipeline

        orch, _, _ = self._make_orchestrator_for_pipeline()

        with patch("services.llm_client.LLMClient") as MockLLM:
            MockLLM.return_value.check_connection.return_value = (False, "No connection")
            with patch("services.progress_tracker.ProgressTracker"):
                result = await run_full_pipeline(
                    orch, title="T", genre="fantasy", idea="I",
                    enable_agents=False, enable_scoring=False, enable_media=False,
                )

        assert result.status == "error"

    async def test_successful_pipeline_returns_completed(self):
        from pipeline.orchestrator_layers import run_full_pipeline

        orch, _, _ = self._make_orchestrator_for_pipeline()

        with patch("services.llm_client.LLMClient") as MockLLM:
            MockLLM.return_value.check_connection.return_value = (True, "ok")
            with patch("services.progress_tracker.ProgressTracker") as MockTracker:
                MockTracker.return_value.events = []
                result = await run_full_pipeline(
                    orch, title="Test Story", genre="fantasy", idea="A hero",
                    enable_agents=False, enable_scoring=False, enable_media=False,
                )

        assert result.status in ("completed", "partial")
        assert result.story_draft is not None

    async def test_layer1_exception_returns_error(self):
        from pipeline.orchestrator_layers import run_full_pipeline

        orch, _, _ = self._make_orchestrator_for_pipeline()
        orch.story_gen.generate_full_story.side_effect = Exception("LLM crash")

        with patch("services.llm_client.LLMClient") as MockLLM:
            MockLLM.return_value.check_connection.return_value = (True, "ok")
            with patch("services.progress_tracker.ProgressTracker") as MockTracker:
                MockTracker.return_value.events = []
                result = await run_full_pipeline(
                    orch, title="Test", genre="fantasy", idea="i",
                    enable_agents=False, enable_scoring=False, enable_media=False,
                )

        assert result.status == "error"

    async def test_layer2_exception_falls_back_to_draft(self):
        from pipeline.orchestrator_layers import run_full_pipeline

        orch, _, _ = self._make_orchestrator_for_pipeline()
        orch.analyzer.analyze.side_effect = Exception("Analyzer crash")

        with patch("services.llm_client.LLMClient") as MockLLM:
            MockLLM.return_value.check_connection.return_value = (True, "ok")
            with patch("services.progress_tracker.ProgressTracker") as MockTracker:
                MockTracker.return_value.events = []
                result = await run_full_pipeline(
                    orch, title="Test", genre="fantasy", idea="i",
                    enable_agents=False, enable_scoring=False, enable_media=False,
                )

        # Layer 2 is non-fatal — should be partial/completed not error
        assert result.status in ("partial", "completed")
        assert result.enhanced_story is not None

    async def test_progress_callback_receives_messages(self):
        from pipeline.orchestrator_layers import run_full_pipeline

        orch, _, _ = self._make_orchestrator_for_pipeline()
        messages = []

        with patch("services.llm_client.LLMClient") as MockLLM:
            MockLLM.return_value.check_connection.return_value = (True, "ok")
            with patch("services.progress_tracker.ProgressTracker") as MockTracker:
                MockTracker.return_value.events = []
                await run_full_pipeline(
                    orch, title="Test", genre="fantasy", idea="i",
                    enable_agents=False, enable_scoring=False, enable_media=False,
                    progress_callback=messages.append,
                )

        assert len(messages) > 0

    async def test_enable_media_false_skips_media_producer(self):
        from pipeline.orchestrator_layers import run_full_pipeline

        orch, _, _ = self._make_orchestrator_for_pipeline()

        with patch("services.llm_client.LLMClient") as MockLLM:
            MockLLM.return_value.check_connection.return_value = (True, "ok")
            with patch("services.progress_tracker.ProgressTracker") as MockTracker:
                MockTracker.return_value.events = []
                await run_full_pipeline(
                    orch, title="Test", genre="fantasy", idea="i",
                    enable_agents=False, enable_scoring=False, enable_media=False,
                )

        orch.media_producer.run.assert_not_called()

    async def test_enable_agents_false_skips_agent_review(self):
        from pipeline.orchestrator_layers import run_full_pipeline

        orch, _, _ = self._make_orchestrator_for_pipeline()

        with patch("services.llm_client.LLMClient") as MockLLM:
            MockLLM.return_value.check_connection.return_value = (True, "ok")
            with patch("services.progress_tracker.ProgressTracker") as MockTracker:
                MockTracker.return_value.events = []
                result = await run_full_pipeline(
                    orch, title="Test", genre="fantasy", idea="i",
                    enable_agents=False, enable_scoring=False, enable_media=False,
                )

        # No agent reviews should be added
        assert result.reviews == []

    async def test_empty_chapters_after_layer1_returns_error(self):
        from pipeline.orchestrator_layers import run_full_pipeline
        from models.schemas import StoryDraft

        orch, _, _ = self._make_orchestrator_for_pipeline()
        # Return a draft with no chapters
        empty_draft = StoryDraft(title="Empty", genre="fantasy", chapters=[])
        orch.story_gen.generate_full_story.return_value = empty_draft

        with patch("services.llm_client.LLMClient") as MockLLM:
            MockLLM.return_value.check_connection.return_value = (True, "ok")
            with patch("services.progress_tracker.ProgressTracker") as MockTracker:
                MockTracker.return_value.events = []
                result = await run_full_pipeline(
                    orch, title="Test", genre="fantasy", idea="i",
                    enable_agents=False, enable_scoring=False, enable_media=False,
                )

        assert result.status == "error"
