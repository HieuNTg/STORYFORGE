"""Integration tests for pipeline Layer 1→2→3 data flow (mocked LLM)."""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.schemas import (
    EnhancedStory, PipelineOutput, SimulationResult, SimulationEvent,
    StoryDraft, VideoScript, StoryboardPanel, VoiceLine, ShotType,
)
from api.pipeline_routes import router


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def api_client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def minimal_draft(sample_characters, sample_chapters, sample_world, sample_outlines):
    return StoryDraft(title="Test Story", genre="tien_hiep", synopsis="A test tale",
                      characters=sample_characters, world=sample_world,
                      outlines=sample_outlines, chapters=sample_chapters)


@pytest.fixture
def minimal_enhanced(sample_chapters):
    return EnhancedStory(title="Test Story (Enhanced)", genre="tien_hiep",
                         chapters=sample_chapters, drama_score=0.7,
                         enhancement_notes=["Test enhancement"])


@pytest.fixture
def minimal_sim():
    return SimulationResult(
        events=[SimulationEvent(round_number=1, event_type="confrontation",
                                description="Fight", drama_score=0.8,
                                characters_involved=["A", "B"])],
        drama_suggestions=["Add twist"],
    )


@pytest.fixture
def minimal_video():
    return VideoScript(
        title="Test Video", total_duration_seconds=60.0,
        panels=[StoryboardPanel(panel_number=1, chapter_number=1, shot_type=ShotType.WIDE,
                                description="Opening", dialogue="Begin.", mood="calm")],
        voice_lines=[VoiceLine(character="Hero", text="Begin.", emotion="calm")],
    )


# ── Layer data flow ───────────────────────────────────────────────────────────

def test_layer1_output_stored_in_pipeline_output(minimal_draft):
    output = PipelineOutput()
    output.story_draft = minimal_draft
    output.current_layer = 1
    assert output.story_draft.title == "Test Story"
    assert len(output.story_draft.chapters) == 3


def test_layer2_receives_draft_from_layer1(minimal_draft, minimal_enhanced, minimal_sim):
    mock_analyzer = MagicMock()
    mock_analyzer.analyze.return_value = {"relationships": []}
    mock_simulator = MagicMock()
    mock_simulator.run_simulation.return_value = minimal_sim
    mock_enhancer = MagicMock()
    mock_enhancer.enhance_with_feedback.return_value = minimal_enhanced

    analysis = mock_analyzer.analyze(minimal_draft)
    sim = mock_simulator.run_simulation(characters=minimal_draft.characters,
                                        relationships=analysis["relationships"],
                                        genre=minimal_draft.genre, num_rounds=3)
    mock_enhancer.enhance_with_feedback(draft=minimal_draft, sim_result=sim)

    mock_analyzer.analyze.assert_called_once_with(minimal_draft)
    assert mock_enhancer.enhance_with_feedback.call_args.kwargs["draft"] is minimal_draft


def test_layer3_receives_enhanced_story(minimal_enhanced, minimal_video, sample_characters):
    mock_sb = MagicMock()
    mock_sb.generate_full_video_script.return_value = minimal_video

    script = mock_sb.generate_full_video_script(
        story=minimal_enhanced, characters=sample_characters, shots_per_chapter=4)

    assert mock_sb.generate_full_video_script.call_args.kwargs["story"] is minimal_enhanced
    assert script.title == "Test Video"


def test_full_pipeline_output_has_all_layers(minimal_draft, minimal_enhanced, minimal_sim, minimal_video):
    output = PipelineOutput(story_draft=minimal_draft, enhanced_story=minimal_enhanced,
                            simulation_result=minimal_sim, video_script=minimal_video,
                            status="completed", current_layer=3, progress=1.0)
    assert output.story_draft.genre == "tien_hiep"
    assert output.enhanced_story.drama_score == 0.7
    assert output.simulation_result.events[0].drama_score == 0.8
    assert output.video_script.total_duration_seconds == 60.0
    assert output.status == "completed"


# ── Checkpoint save / resume ───────────────────────────────────────────────────

def test_save_then_reload_preserves_data(tmp_path, minimal_draft, minimal_enhanced):
    from pipeline.orchestrator_checkpoint import CheckpointManager
    import pipeline.orchestrator_checkpoint as ckpt_mod

    output = PipelineOutput(story_draft=minimal_draft, enhanced_story=minimal_enhanced,
                            current_layer=2, status="running")
    orig = ckpt_mod.CHECKPOINT_DIR
    ckpt_mod.CHECKPOINT_DIR = str(tmp_path / "ckpts")
    try:
        mgr = CheckpointManager(output=output, analyzer=MagicMock(), simulator=MagicMock(),
                                enhancer=MagicMock(), storyboard_gen=MagicMock())
        path = mgr.save(layer=2, background=False)
        with open(path, "r", encoding="utf-8") as f:
            loaded_data = json.load(f)
    finally:
        ckpt_mod.CHECKPOINT_DIR = orig

    reloaded = PipelineOutput(**loaded_data)
    assert reloaded.story_draft.title == minimal_draft.title
    assert reloaded.enhanced_story.drama_score == minimal_enhanced.drama_score
    assert reloaded.current_layer == 2


def test_resume_from_layer1_runs_layers_2_and_3(tmp_path, minimal_draft, minimal_enhanced, minimal_sim, minimal_video):
    from pipeline.orchestrator_checkpoint import CheckpointManager
    import pipeline.orchestrator_checkpoint as ckpt_mod

    output = PipelineOutput(story_draft=minimal_draft, current_layer=1, status="running")
    ckpt_file = tmp_path / "layer1.json"
    ckpt_file.write_text(output.model_dump_json(), encoding="utf-8")

    mock_analyzer = MagicMock()
    mock_analyzer.analyze.return_value = {"relationships": []}
    mock_simulator = MagicMock()
    mock_simulator.run_simulation.return_value = minimal_sim
    mock_enhancer = MagicMock()
    mock_enhancer.enhance_with_feedback.return_value = minimal_enhanced
    mock_sb = MagicMock()
    mock_sb.generate_full_video_script.return_value = minimal_video

    orig = ckpt_mod.CHECKPOINT_DIR
    ckpt_mod.CHECKPOINT_DIR = str(tmp_path)
    try:
        mgr = CheckpointManager(output=PipelineOutput(), analyzer=mock_analyzer,
                                simulator=mock_simulator, enhancer=mock_enhancer,
                                storyboard_gen=mock_sb)
        result = mgr.resume(str(ckpt_file), enable_agents=False, enable_scoring=False)
    finally:
        ckpt_mod.CHECKPOINT_DIR = orig

    mock_analyzer.analyze.assert_called_once()
    mock_enhancer.enhance_with_feedback.assert_called_once()
    mock_sb.generate_full_video_script.assert_called_once()
    assert result.enhanced_story is not None
    assert result.video_script is not None


def test_resume_from_layer2_skips_layer2(tmp_path, minimal_draft, minimal_enhanced, minimal_video):
    from pipeline.orchestrator_checkpoint import CheckpointManager
    import pipeline.orchestrator_checkpoint as ckpt_mod

    output = PipelineOutput(story_draft=minimal_draft, enhanced_story=minimal_enhanced,
                            current_layer=2, status="running")
    ckpt_file = tmp_path / "layer2.json"
    ckpt_file.write_text(output.model_dump_json(), encoding="utf-8")

    mock_analyzer = MagicMock()
    mock_sb = MagicMock()
    mock_sb.generate_full_video_script.return_value = minimal_video

    orig = ckpt_mod.CHECKPOINT_DIR
    ckpt_mod.CHECKPOINT_DIR = str(tmp_path)
    try:
        mgr = CheckpointManager(output=PipelineOutput(), analyzer=mock_analyzer,
                                simulator=MagicMock(), enhancer=MagicMock(),
                                storyboard_gen=mock_sb)
        mgr.resume(str(ckpt_file), enable_agents=False, enable_scoring=False)
    finally:
        ckpt_mod.CHECKPOINT_DIR = orig

    mock_analyzer.analyze.assert_not_called()
    mock_sb.generate_full_video_script.assert_called_once()


def test_resume_corrupted_checkpoint_raises(tmp_path):
    from pipeline.orchestrator_checkpoint import CheckpointManager

    bad = tmp_path / "corrupt.json"
    bad.write_text("{{INVALID", encoding="utf-8")

    mgr = CheckpointManager(output=PipelineOutput(), analyzer=MagicMock(),
                            simulator=MagicMock(), enhancer=MagicMock(),
                            storyboard_gen=MagicMock())
    with pytest.raises(ValueError, match="corrupted"):
        mgr.resume(str(bad))


# ── SSE event ordering ─────────────────────────────────────────────────────────

def _parse_sse(raw: bytes) -> list:
    events = []
    for line in raw.decode("utf-8").splitlines():
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


def test_error_sse_on_short_idea(api_client):
    resp = api_client.post("/pipeline/run", json={"idea": "short"})
    events = _parse_sse(resp.content)
    assert any(ev.get("type") == "error" for ev in events)


def test_session_event_is_first(api_client):
    long_idea = "A hero emerges to challenge the dark empire ruling the ancient land."
    mock_output = PipelineOutput(status="completed", current_layer=3, progress=1.0)

    with patch("api.pipeline_routes.PipelineOrchestrator") as mock_cls, \
         patch("services.llm_client.LLMClient") as mock_llm_cls:
        mock_llm = MagicMock()
        mock_llm.check_connection.return_value = (True, "ok")
        mock_llm_cls.return_value = mock_llm
        mock_orch = MagicMock()
        mock_orch.run_full_pipeline.return_value = mock_output
        mock_cls.return_value = mock_orch

        resp = api_client.post("/pipeline/run", json={
            "idea": long_idea, "genre": "tien_hiep",
            "num_chapters": 1, "enable_agents": False, "enable_scoring": False,
        })

    events = _parse_sse(resp.content)
    assert events and events[0]["type"] == "session"
    assert "session_id" in events[0]
