"""Tests for continuation history sidecar — Piece K.

Covers the advisory ``<checkpoint>.history.json`` machinery:
- record_continuation: append, fresh create, rotation at 20 events
- failure tolerance: write errors must not raise
- /api/pipeline/continuation/{filename}/history endpoint
- /api/pipeline/checkpoints attaches latest_continuation
"""

import json
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services import continuation_history
from services.continuation_history import (
    _MAX_EVENTS,
    latest_event,
    read_events,
    record_continuation,
    sidecar_path_for,
    slug_for_title,
)


# --------------------------------------------------------------------------- helpers


@pytest.fixture(autouse=True)
def _isolated_checkpoint_dir(tmp_path, monkeypatch):
    """Redirect checkpoint_dir() to a tmp folder for the duration of the test."""
    monkeypatch.setattr(continuation_history, "checkpoint_dir", lambda: tmp_path)
    yield tmp_path


# --------------------------------------------------------------------------- sidecar write


def test_record_creates_fresh_sidecar(tmp_path):
    record_continuation(title="My Story", previous_chapter_count=5, new_chapter_count=8, layer=1)
    path = sidecar_path_for("My_Story_layer1.json")
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data["events"]) == 1
    ev = data["events"][0]
    assert ev["previous_chapter_count"] == 5
    assert ev["new_chapter_count"] == 8
    assert ev["added"] == 3
    assert ev["ts"].endswith("Z")


def test_record_appends_to_existing(tmp_path):
    record_continuation(title="Ts", previous_chapter_count=1, new_chapter_count=2, layer=1)
    record_continuation(title="Ts", previous_chapter_count=2, new_chapter_count=5, layer=1)
    events = read_events(f"{slug_for_title('Ts')}_layer1.json")
    assert len(events) == 2
    assert events[0]["added"] == 1
    assert events[1]["added"] == 3


def test_record_rotates_at_max(tmp_path):
    title = "Rot"
    for i in range(_MAX_EVENTS + 5):
        record_continuation(title=title, previous_chapter_count=i, new_chapter_count=i + 1, layer=1)
    events = read_events(f"{slug_for_title(title)}_layer1.json")
    assert len(events) == _MAX_EVENTS
    # Newest events kept; oldest 5 dropped — first kept event has prev_count == 5.
    assert events[0]["previous_chapter_count"] == 5
    assert events[-1]["previous_chapter_count"] == _MAX_EVENTS + 4


def test_record_skips_when_no_chapters_added(tmp_path):
    result = record_continuation(title="X", previous_chapter_count=3, new_chapter_count=3, layer=1)
    assert result is None
    assert not sidecar_path_for("X_layer1.json").exists()


def test_record_failure_does_not_raise(tmp_path, monkeypatch):
    """Write errors must be swallowed — sidecar is advisory only."""
    def _boom(*_a, **_kw):
        raise OSError("disk full")

    monkeypatch.setattr("builtins.open", _boom)
    # Should not raise.
    result = record_continuation(title="Y", previous_chapter_count=1, new_chapter_count=2, layer=1)
    assert result is None


def test_continue_story_hook_swallows_sidecar_failure(tmp_path):
    """The orchestrator hook must not propagate sidecar failures to the caller.

    Simulates the StoryContinuation.continue_story flow: if record_continuation
    blows up for any reason, the continuation must still return a draft.
    """
    from unittest.mock import MagicMock
    from pipeline.orchestrator_continuation import StoryContinuation
    from models.schemas import Chapter, PipelineOutput, StoryDraft

    draft_before = StoryDraft(
        title="HookSafe", genre="g", synopsis="s",
        chapters=[Chapter(chapter_number=1, title="C1", content="x", word_count=1)],
    )
    output = PipelineOutput(story_draft=draft_before, status="ok")

    fake_gen = MagicMock()
    draft_after = StoryDraft(
        title="HookSafe", genre="g", synopsis="s",
        chapters=draft_before.chapters + [
            Chapter(chapter_number=2, title="C2", content="y", word_count=1),
        ],
    )
    fake_gen.continue_story.return_value = draft_after

    fake_ckpt_mgr = MagicMock()
    cont = StoryContinuation(
        output=output, story_gen=fake_gen,
        analyzer=MagicMock(), simulator=MagicMock(), enhancer=MagicMock(),
        checkpoint_manager=fake_ckpt_mgr,
    )

    with patch(
        "services.continuation_history.record_continuation",
        side_effect=RuntimeError("sidecar exploded"),
    ):
        result = cont.continue_story(additional_chapters=1)
    assert len(result.chapters) == 2
    assert fake_ckpt_mgr.save.called


# --------------------------------------------------------------------------- read endpoint


@pytest.fixture
def client(monkeypatch, tmp_path):
    """Mount continuation_routes in isolation; redirect _CHECKPOINT_DIR to tmp."""
    from api import continuation_routes

    monkeypatch.setattr(continuation_routes, "_CHECKPOINT_DIR", tmp_path.resolve())
    monkeypatch.setattr(continuation_history, "checkpoint_dir", lambda: tmp_path)

    app = FastAPI()
    app.include_router(continuation_routes.router)
    return TestClient(app)


def test_history_endpoint_empty_for_missing_sidecar(client):
    r = client.get("/pipeline/continuation/never_existed_layer1.json/history")
    assert r.status_code == 200
    assert r.json() == {"events": []}


def test_history_endpoint_returns_events(client, tmp_path):
    record_continuation(title="Hist", previous_chapter_count=2, new_chapter_count=4, layer=1)
    r = client.get(f"/pipeline/continuation/{slug_for_title('Hist')}_layer1.json/history")
    assert r.status_code == 200
    body = r.json()
    assert len(body["events"]) == 1
    assert body["events"][0]["added"] == 2


def test_history_endpoint_blocks_path_traversal(client):
    r = client.get("/pipeline/continuation/..%2F..%2Fetc%2Fpasswd/history")
    # FastAPI normalizes %2F; with traversal, validator returns 400.
    assert r.status_code in (400, 404)


# --------------------------------------------------------------------------- /pipeline/checkpoints attachment


def test_pipeline_checkpoints_attaches_latest_continuation(monkeypatch, tmp_path):
    """The list endpoint must surface the latest event as latest_continuation."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api import pipeline_routes

    monkeypatch.setattr(continuation_history, "checkpoint_dir", lambda: tmp_path)

    record_continuation(title="ListMe", previous_chapter_count=4, new_chapter_count=7, layer=1)

    fake_ckpts = [
        {
            "file": f"{slug_for_title('ListMe')}_layer1.json",
            "modified": "2026-05-03 21:00",
            "size_kb": 3,
            "title": "ListMe",
            "genre": "fantasy",
            "chapter_count": 7,
            "current_layer": 1,
        },
        {
            "file": "no_history_layer1.json",
            "modified": "2026-05-01 10:00",
            "size_kb": 2,
            "title": "Nope",
            "genre": "",
            "chapter_count": 3,
            "current_layer": 1,
        },
    ]

    with patch("pipeline.orchestrator.PipelineOrchestrator.list_checkpoints", return_value=fake_ckpts):
        app = FastAPI()
        app.include_router(pipeline_routes.router)
        client = TestClient(app)
        r = client.get("/pipeline/checkpoints")
    assert r.status_code == 200
    items = r.json()["checkpoints"]
    by_path = {c["path"]: c for c in items}
    assert by_path[fake_ckpts[0]["file"]]["latest_continuation"]["added"] == 3
    assert by_path["no_history_layer1.json"]["latest_continuation"] is None


# --------------------------------------------------------------------------- helpers


def test_latest_event_helper_returns_newest():
    record_continuation(title="L", previous_chapter_count=1, new_chapter_count=2, layer=1)
    record_continuation(title="L", previous_chapter_count=2, new_chapter_count=10, layer=1)
    ev = latest_event(f"{slug_for_title('L')}_layer1.json")
    assert ev is not None
    assert ev["added"] == 8


def test_slug_matches_checkpoint_manager_rule():
    """Slug rule: title[:30] then non-word → _ (mirrors CheckpointManager.save)."""
    import re
    # Pure-ASCII case is the tightest contract; Unicode handling matches \w in re.
    assert slug_for_title("My Title!! ") == re.sub(r"[^\w\-]", "_", "My Title!! ")
    assert slug_for_title("") == "untitled"
    # Truncation: title >30 chars gets cut at 30 before sanitization.
    long = "x" * 50
    assert slug_for_title(long) == "x" * 30


# --------------------------------------------------------------------------- Piece N: resume status


def test_resume_status_flags_interrupted_when_chapters_below_target(tmp_path):
    """chapters_written < outline_count and no recent continuation → interrupted."""
    from services.resume_status import derive_resume_status

    ckpt = {
        "file": "stuck_layer1.json",
        "chapter_count": 3,
        "outline_count": 10,
    }
    status = derive_resume_status(ckpt)
    assert status == {
        "interrupted": True,
        "resume_from_chapter": 4,
        "target_chapters": 10,
    }


def test_resume_status_clear_when_complete(tmp_path):
    """chapters_written >= outline_count → never interrupted."""
    from services.resume_status import derive_resume_status

    ckpt = {"file": "done_layer1.json", "chapter_count": 10, "outline_count": 10}
    status = derive_resume_status(ckpt)
    assert status["interrupted"] is False
    assert status["resume_from_chapter"] is None
    assert status["target_chapters"] == 10


def test_resume_status_clear_when_recent_continuation(tmp_path):
    """A successful continuation in the last 6h suppresses the affordance."""
    from services.resume_status import derive_resume_status

    record_continuation(title="Recovered", previous_chapter_count=3, new_chapter_count=4, layer=1)
    ckpt = {
        "file": f"{slug_for_title('Recovered')}_layer1.json",
        "chapter_count": 4,  # still below target …
        "outline_count": 10,  # … but recent event means user already resumed.
    }
    status = derive_resume_status(ckpt)
    assert status["interrupted"] is False
    assert status["resume_from_chapter"] is None


def test_resume_status_interrupted_when_history_is_old(tmp_path, monkeypatch):
    """Stale (>6h) history events do NOT cover an ongoing interrupt."""
    from services.resume_status import derive_resume_status

    # Write an event manually with a stale timestamp (10h ago).
    sidecar = sidecar_path_for("Stale_layer1.json")
    sidecar.write_text(
        json.dumps({"events": [{
            "ts": "2020-01-01T00:00:00Z",
            "previous_chapter_count": 1,
            "new_chapter_count": 2,
            "added": 1,
        }]}),
        encoding="utf-8",
    )

    ckpt = {"file": "Stale_layer1.json", "chapter_count": 2, "outline_count": 10}
    status = derive_resume_status(ckpt)
    assert status["interrupted"] is True
    assert status["resume_from_chapter"] == 3


def test_resume_status_clear_when_target_unknown():
    """Old checkpoints without outlines → outline_count=0 → not interrupted."""
    from services.resume_status import derive_resume_status

    ckpt = {"file": "legacy_layer1.json", "chapter_count": 0, "outline_count": 0}
    status = derive_resume_status(ckpt)
    assert status["interrupted"] is False


def test_pipeline_checkpoints_attaches_resume_fields(monkeypatch, tmp_path):
    """The list endpoint must surface interrupted/resume_from_chapter/target_chapters."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api import pipeline_routes

    monkeypatch.setattr(continuation_history, "checkpoint_dir", lambda: tmp_path)

    fake_ckpts = [
        # Story stuck at chapter 4 of 10; no history → interrupted.
        {
            "file": "stuck_layer1.json",
            "modified": "2026-05-03 21:00",
            "size_kb": 3,
            "title": "Stuck",
            "genre": "x",
            "chapter_count": 4,
            "current_layer": 1,
            "outline_count": 10,
        },
        # Story complete; 5 == 5 → not interrupted.
        {
            "file": "complete_layer1.json",
            "modified": "2026-05-03 21:00",
            "size_kb": 3,
            "title": "Done",
            "genre": "x",
            "chapter_count": 5,
            "current_layer": 1,
            "outline_count": 5,
        },
    ]

    with patch("pipeline.orchestrator.PipelineOrchestrator.list_checkpoints", return_value=fake_ckpts):
        app = FastAPI()
        app.include_router(pipeline_routes.router)
        client = TestClient(app)
        r = client.get("/pipeline/checkpoints")
    assert r.status_code == 200
    by_path = {c["path"]: c for c in r.json()["checkpoints"]}

    assert by_path["stuck_layer1.json"]["interrupted"] is True
    assert by_path["stuck_layer1.json"]["resume_from_chapter"] == 5
    assert by_path["stuck_layer1.json"]["target_chapters"] == 10

    assert by_path["complete_layer1.json"]["interrupted"] is False
    assert by_path["complete_layer1.json"]["resume_from_chapter"] is None
    assert by_path["complete_layer1.json"]["target_chapters"] == 5
