"""Tests for /api/images/{session_id}/generate endpoint."""

import pytest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.image_routes import router as image_router, _in_flight
from models.schemas import Chapter, StoryDraft, PipelineOutput


def _build_orch(num_chapters: int = 2):
    chapters = [
        Chapter(chapter_number=i, title=f"Ch{i}", content=f"Body {i}", word_count=2)
        for i in range(1, num_chapters + 1)
    ]
    draft = StoryDraft(title="T", genre="g", synopsis="s", chapters=chapters)
    output = PipelineOutput(story_draft=draft, status="complete")

    class _Wrap:
        def __init__(self, out):
            self.output = out
    return _Wrap(output)


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(image_router)
    _in_flight.clear()
    return TestClient(app)


def test_generate_404_when_session_missing(client):
    with patch("api.image_routes._get_story_data", return_value=None):
        r = client.post("/images/missing/generate", json={})
    assert r.status_code == 404


def test_generate_provider_none_short_circuits(client):
    orch = _build_orch(2)
    with patch("api.image_routes._get_story_data", return_value=orch), \
         patch("services.handlers.handle_generate_images", return_value=([], "no provider")):
        r = client.post("/images/sess-1/generate", json={"provider": "none"})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0
    assert body["chapter_images"] == {}


def test_generate_persists_chapter_images(client, tmp_path, monkeypatch):
    # Simulate handler writing image filenames onto chapter.images
    orch = _build_orch(3)

    def fake_handler(orch_state, provider="none"):
        for i, ch in enumerate(orch_state.output.story_draft.chapters, 1):
            ch.images = [f"ch{ch.chapter_number:02d}_panel01.png"]
        return [c.images[0] for c in orch_state.output.story_draft.chapters], "ok"

    with patch("api.image_routes._get_story_data", return_value=orch), \
         patch("services.handlers.handle_generate_images", side_effect=fake_handler):
        r = client.post("/images/sess-2/generate", json={"provider": "dalle"})

    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 3
    assert body["chapter_images"] == {
        "1": ["ch01_panel01.png"],
        "2": ["ch02_panel01.png"],
        "3": ["ch03_panel01.png"],
    }


def test_generate_in_flight_guard(client):
    orch = _build_orch(1)
    _in_flight.add("locked-sess")
    try:
        with patch("api.image_routes._get_story_data", return_value=orch):
            r = client.post("/images/locked-sess/generate", json={})
        assert r.status_code == 409
    finally:
        _in_flight.discard("locked-sess")
