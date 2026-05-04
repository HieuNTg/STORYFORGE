"""FastAPI TestClient tests for GET /api/diagnostics/semantic/{story_id} (Sprint 2 P6)."""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FULL_RESULT = {
    "story_id": "test-story-id",
    "outline_metrics": {
        "schema_version": "1.0.0",
        "conflict_web_density": 0.50,
        "arc_trajectory_variance": 0.40,
        "pacing_distribution_skew": 0.70,
        "beat_coverage_ratio": 0.80,
        "character_screen_time_gini": 0.20,
        "overall_score": 0.72,
        "num_chapters": 5,
        "num_characters": 3,
        "num_conflict_nodes": 3,
        "num_seeds": 4,
        "num_arc_waypoints": 6,
    },
    "per_chapter": [
        {
            "chapter_num": 1,
            "semantic_findings": None,
            "contract": None,
        }
    ],
    "summary": {
        "total_payoff_matched": 2,
        "total_payoff_weak": 0,
        "total_payoff_missed": 1,
        "total_structural_findings_by_severity": {
            "critical": 0,
            "major": 1,
            "minor": 2,
        },
        "outline_floors_violated": [],
    },
}


@pytest.fixture()
def client():
    from fastapi import FastAPI
    from api.diagnostics_routes import router
    _app = FastAPI()
    _app.include_router(router, prefix="/api")
    return TestClient(_app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSemanticDiagnosticsEndpoint:
    def test_404_story_not_found(self, client, monkeypatch):
        """Non-existent story_id → 404."""
        import services.diagnostics_service as svc
        monkeypatch.setattr(svc, "build_semantic_diagnostics", lambda sid: None)

        resp = client.get("/api/diagnostics/semantic/nonexistent-id")
        assert resp.status_code == 404
        data = resp.json()
        assert "detail" in data

    def test_404_pre_sprint2_story(self, client, monkeypatch):
        """Story exists but no Sprint-2 data → 404."""
        import services.diagnostics_service as svc
        monkeypatch.setattr(svc, "build_semantic_diagnostics", lambda sid: None)

        resp = client.get("/api/diagnostics/semantic/some-story-id")
        assert resp.status_code == 404

    def test_200_with_full_data(self, client, monkeypatch):
        """Story with Sprint-2 data → 200 + correct shape."""
        import services.diagnostics_service as svc

        sid = str(uuid.uuid4())
        result = dict(_FULL_RESULT)
        result["story_id"] = sid
        monkeypatch.setattr(
            svc,
            "build_semantic_diagnostics",
            lambda s: result if s == sid else None,
        )

        resp = client.get(f"/api/diagnostics/semantic/{sid}")
        assert resp.status_code == 200
        body = resp.json()

        assert body["story_id"] == sid
        assert "outline_metrics" in body
        assert "per_chapter" in body
        assert "summary" in body
        summary = body["summary"]
        assert summary["total_payoff_matched"] == 2
        assert summary["total_payoff_missed"] == 1
        assert "total_structural_findings_by_severity" in summary
        assert summary["total_structural_findings_by_severity"]["critical"] == 0

    def test_response_content_type_is_json(self, client, monkeypatch):
        """Response Content-Type is application/json."""
        import services.diagnostics_service as svc

        sid = str(uuid.uuid4())
        monkeypatch.setattr(
            svc,
            "build_semantic_diagnostics",
            lambda s: dict(_FULL_RESULT, story_id=s),
        )

        resp = client.get(f"/api/diagnostics/semantic/{sid}")
        assert resp.status_code == 200
        assert "application/json" in resp.headers.get("content-type", "")

    def test_existing_handoff_endpoint_unchanged(self, client, monkeypatch):
        """Verify the Sprint-1 handoff endpoint is not broken by the new endpoint."""
        import services.diagnostics_service as svc
        monkeypatch.setattr(svc, "build_handoff_diagnostics", lambda sid: None)

        resp = client.get("/api/diagnostics/handoff/nonexistent-id")
        assert resp.status_code == 404
