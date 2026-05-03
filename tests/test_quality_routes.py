"""Tests for /api/quality/{session_id} — read-only L1/L2 score surface."""

import pytest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.quality_routes import router as quality_router
from models.schemas import (
    Chapter,
    ChapterScore,
    PipelineOutput,
    StoryDraft,
    StoryScore,
)


def _build_orch(quality_scores=None, num_chapters: int = 2):
    chapters = [
        Chapter(chapter_number=i, title=f"Ch {i}", content=f"body {i}", word_count=2)
        for i in range(1, num_chapters + 1)
    ]
    draft = StoryDraft(title="T", genre="g", synopsis="s", chapters=chapters)
    output = PipelineOutput(
        story_draft=draft,
        status="complete",
        quality_scores=list(quality_scores or []),
    )

    class _Wrap:
        def __init__(self, out):
            self.output = out

    return _Wrap(output)


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(quality_router)
    return TestClient(app)


def test_quality_404_when_session_missing(client):
    with patch("api.quality_routes._get_story_data", return_value=None):
        r = client.get("/quality/missing-id")
    assert r.status_code == 404


def test_quality_empty_when_no_scores(client):
    """Backwards-compat: legacy checkpoints without scores must not error."""
    orch = _build_orch(quality_scores=[], num_chapters=3)
    with patch("api.quality_routes._get_story_data", return_value=orch):
        r = client.get("/quality/legacy-sess")
    assert r.status_code == 200
    body = r.json()
    assert body["overall"] is None
    assert body["chapters"] == []


def test_quality_returns_l1_scores(client):
    cs1 = ChapterScore(chapter_number=1, coherence=4.0, character_consistency=3.5,
                       drama=4.5, writing_quality=4.0, notes="strong hook")
    cs1.overall = 4.0
    cs2 = ChapterScore(chapter_number=2, coherence=3.0, character_consistency=3.0,
                       drama=2.5, writing_quality=3.0)
    cs2.overall = 2.875
    story_score = StoryScore(
        chapter_scores=[cs1, cs2],
        avg_coherence=3.5, avg_character=3.25, avg_drama=3.5, avg_writing=3.5,
        overall=3.4375, weakest_chapter=2, scoring_layer=1,
    )
    orch = _build_orch(quality_scores=[story_score], num_chapters=2)

    with patch("api.quality_routes._get_story_data", return_value=orch):
        r = client.get("/quality/sess-1")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["overall"]["scoring_layer"] == 1
    assert body["overall"]["weakest_chapter"] == 2
    assert len(body["chapters"]) == 2
    ch1 = body["chapters"][0]
    assert ch1["chapter_number"] == 1
    assert ch1["title"] == "Ch 1"
    assert ch1["scoring_layer"] == 1
    assert ch1["scores"]["drama"] == 4.5
    assert ch1["notes"] == "strong hook"


def test_quality_l2_overrides_l1(client):
    """When both L1 and L2 scored a chapter, L2 wins."""
    l1_cs1 = ChapterScore(chapter_number=1, drama=2.0)
    l1_cs1.overall = 2.0
    l1 = StoryScore(chapter_scores=[l1_cs1], overall=2.0, scoring_layer=1)

    l2_cs1 = ChapterScore(chapter_number=1, drama=4.5)
    l2_cs1.overall = 4.5
    l2 = StoryScore(chapter_scores=[l2_cs1], overall=4.5, scoring_layer=2)

    orch = _build_orch(quality_scores=[l1, l2], num_chapters=1)
    with patch("api.quality_routes._get_story_data", return_value=orch):
        r = client.get("/quality/sess-merge")

    assert r.status_code == 200
    body = r.json()
    # Overall must come from the latest layer (L2)
    assert body["overall"]["scoring_layer"] == 2
    assert body["overall"]["overall"] == 4.5
    # Chapter must reflect L2 score
    assert body["chapters"][0]["scoring_layer"] == 2
    assert body["chapters"][0]["scores"]["drama"] == 4.5


def test_quality_response_schema_validates(client):
    """The response model must validate cleanly for typical scored output."""
    cs = ChapterScore(chapter_number=1, coherence=3.0, character_consistency=3.0,
                      drama=3.0, writing_quality=3.0, thematic_alignment=2.0,
                      dialogue_depth=1.5)
    cs.overall = 3.0
    ss = StoryScore(chapter_scores=[cs], overall=3.0, scoring_layer=1)
    orch = _build_orch(quality_scores=[ss], num_chapters=1)

    with patch("api.quality_routes._get_story_data", return_value=orch):
        r = client.get("/quality/schema-check")

    assert r.status_code == 200
    body = r.json()
    # Required keys on every chapter entry
    required_score_keys = {
        "coherence", "character_consistency", "drama", "writing_quality",
        "thematic_alignment", "dialogue_depth", "overall",
    }
    for ch in body["chapters"]:
        assert required_score_keys.issubset(ch["scores"].keys())
        assert "chapter_number" in ch
        assert "scoring_layer" in ch
