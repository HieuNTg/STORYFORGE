"""Tests for Story Library — checkpoint list/get/delete endpoints and metadata."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.pipeline_routes import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _write_checkpoint(directory, filename, data: dict):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _minimal_pipeline_data(title="Test Story", genre="tien_hiep", chapter_count=3):
    chapters = [
        {"chapter_number": i, "title": f"Ch {i}", "content": "text", "summary": "s"}
        for i in range(1, chapter_count + 1)
    ]
    return {
        "story_draft": {"title": title, "genre": genre, "synopsis": "A story",
                        "characters": [], "world": {"name": "W", "description": "D",
                        "rules": [], "locations": [], "era": ""}, "outlines": [],
                        "chapters": chapters},
        "enhanced_story": {"title": title, "genre": genre, "chapters": chapters,
                           "drama_score": 0.7, "enhancement_notes": []},
        "simulation_result": None, "video_script": None, "status": "completed",
        "current_layer": 3, "progress": 1.0, "logs": [], "reviews": [],
        "quality_scores": [], "analytics": {}, "knowledge_graph_summary": None,
        "progress_events": [],
    }


# ── GET /pipeline/checkpoints ─────────────────────────────────────────────────

def test_list_checkpoints_empty(client):
    with patch("pipeline.orchestrator.PipelineOrchestrator.list_checkpoints", return_value=[]):
        resp = client.get("/pipeline/checkpoints")
    assert resp.status_code == 200
    assert resp.json() == {"checkpoints": []}


def test_list_checkpoints_fields_shape(client):
    mock_ckpts = [{"file": "story_layer3.json", "modified": "2026-04-02 10:00",
                   "size_kb": 12, "title": "Story Title", "genre": "tien_hiep",
                   "chapter_count": 5, "current_layer": 3}]
    with patch("pipeline.orchestrator.PipelineOrchestrator.list_checkpoints", return_value=mock_ckpts):
        resp = client.get("/pipeline/checkpoints")
    ckpt = resp.json()["checkpoints"][0]
    assert ckpt["path"] == "story_layer3.json"
    assert ckpt["title"] == "Story Title"
    assert ckpt["chapter_count"] == 5
    assert "5KB" not in ckpt["label"] or "12KB" in ckpt["label"]


def test_list_checkpoints_label_includes_size(client):
    mock_ckpts = [{"file": "x.json", "modified": "2026-04-01 08:30", "size_kb": 5,
                   "title": "T", "genre": "k", "chapter_count": 2, "current_layer": 1}]
    with patch("pipeline.orchestrator.PipelineOrchestrator.list_checkpoints", return_value=mock_ckpts):
        resp = client.get("/pipeline/checkpoints")
    label = resp.json()["checkpoints"][0]["label"]
    assert "x.json" in label and "5KB" in label


# ── GET /pipeline/checkpoints/{filename} metadata extraction ──────────────────

def test_metadata_extraction_title_genre_chapters(tmp_path):
    from pipeline.orchestrator_checkpoint import CheckpointManager
    import pipeline.orchestrator_checkpoint as ckpt_mod

    ckpt_dir = tmp_path / "checkpoints"
    _write_checkpoint(ckpt_dir, "dragon_layer3.json", _minimal_pipeline_data("Dragon Sword", "kiem_hiep", 4))

    orig = ckpt_mod.CHECKPOINT_DIR
    ckpt_mod.CHECKPOINT_DIR = str(ckpt_dir)
    try:
        results = CheckpointManager.list_checkpoints()
    finally:
        ckpt_mod.CHECKPOINT_DIR = orig

    assert len(results) == 1
    entry = results[0]
    assert entry["title"] == "Dragon Sword"
    assert entry["genre"] == "kiem_hiep"
    assert entry["chapter_count"] == 4
    assert entry["current_layer"] == 3


def test_metadata_falls_back_to_enhanced_title(tmp_path):
    from pipeline.orchestrator_checkpoint import CheckpointManager
    import pipeline.orchestrator_checkpoint as ckpt_mod

    data = _minimal_pipeline_data("Enhanced Title", "ngon_tinh", 2)
    data["story_draft"]["title"] = ""

    ckpt_dir = tmp_path / "checkpoints"
    _write_checkpoint(ckpt_dir, "enhanced.json", data)

    orig = ckpt_mod.CHECKPOINT_DIR
    ckpt_mod.CHECKPOINT_DIR = str(ckpt_dir)
    try:
        results = CheckpointManager.list_checkpoints()
    finally:
        ckpt_mod.CHECKPOINT_DIR = orig

    assert results[0]["title"] == "Enhanced Title"


def test_corrupted_json_handled_gracefully(tmp_path):
    from pipeline.orchestrator_checkpoint import CheckpointManager
    import pipeline.orchestrator_checkpoint as ckpt_mod

    ckpt_dir = tmp_path / "checkpoints"
    ckpt_dir.mkdir()
    (ckpt_dir / "bad.json").write_text("NOT VALID JSON", encoding="utf-8")

    orig = ckpt_mod.CHECKPOINT_DIR
    ckpt_mod.CHECKPOINT_DIR = str(ckpt_dir)
    try:
        results = CheckpointManager.list_checkpoints()
    finally:
        ckpt_mod.CHECKPOINT_DIR = orig

    assert len(results) == 1
    assert results[0]["title"] == ""
    assert results[0]["chapter_count"] == 0


def test_nonexistent_dir_returns_empty(tmp_path):
    from pipeline.orchestrator_checkpoint import CheckpointManager
    import pipeline.orchestrator_checkpoint as ckpt_mod

    orig = ckpt_mod.CHECKPOINT_DIR
    ckpt_mod.CHECKPOINT_DIR = str(tmp_path / "does_not_exist")
    try:
        assert CheckpointManager.list_checkpoints() == []
    finally:
        ckpt_mod.CHECKPOINT_DIR = orig


# ── GET / DELETE invalid filename ─────────────────────────────────────────────

def test_get_checkpoint_404_for_missing(client):
    with patch("api.pipeline_routes.os.path.exists", return_value=False):
        resp = client.get("/pipeline/checkpoints/missing.json")
    assert resp.status_code == 404


def test_delete_checkpoint_404_for_missing(client):
    with patch("api.pipeline_routes.os.path.exists", return_value=False):
        resp = client.delete("/pipeline/checkpoints/ghost.json")
    assert resp.status_code == 404


def test_delete_checkpoint_calls_remove(client, tmp_path):
    ckpt_dir = tmp_path / "checkpoints"
    ckpt_path = _write_checkpoint(ckpt_dir, "to_delete.json", _minimal_pipeline_data())

    with patch("api.pipeline_routes.os.path.join", return_value=str(ckpt_path)), \
         patch("api.pipeline_routes.os.path.exists", return_value=True), \
         patch("api.pipeline_routes.os.remove") as mock_rm:
        resp = client.delete("/pipeline/checkpoints/to_delete.json")

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    mock_rm.assert_called_once()


# ── CheckpointManager.save ────────────────────────────────────────────────────

def test_save_creates_valid_json_file(tmp_path, sample_pipeline_output):
    from pipeline.orchestrator_checkpoint import CheckpointManager
    import pipeline.orchestrator_checkpoint as ckpt_mod

    orig = ckpt_mod.CHECKPOINT_DIR
    ckpt_mod.CHECKPOINT_DIR = str(tmp_path / "ckpts")
    try:
        mgr = CheckpointManager(output=sample_pipeline_output, analyzer=MagicMock(),
                                simulator=MagicMock(), enhancer=MagicMock())
        path = mgr.save(layer=1, background=False)
    finally:
        ckpt_mod.CHECKPOINT_DIR = orig

    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        saved = json.load(f)
    assert "story_draft" in saved
    assert "layer1" in path
