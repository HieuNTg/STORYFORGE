"""Route tests for api/eval_routes.py (previously untested).

The module-level EvalPipeline instance is patched so tests stay hermetic.
RBAC no-ops in the open-source build, so no auth setup is needed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client() -> TestClient:
    app = FastAPI()
    from api.eval_routes import router

    app.include_router(router, prefix="/api")
    return TestClient(app)


def _patched_pipeline() -> MagicMock:
    pipeline = MagicMock()
    pipeline.submit_human_eval.return_value = {"story_id": "s-1", "avg": 4.0}
    pipeline.run_golden_eval.return_value = {"status": "pass", "regressions": []}
    pipeline.generate_report.return_value = {"story_id": "s-1", "aggregate": 4.2}
    return pipeline


class TestSubmitEval:
    def test_submit_returns_record(self):
        pipeline = _patched_pipeline()
        with patch("api.eval_routes._pipeline", pipeline):
            resp = _client().post(
                "/api/v1/eval/submit",
                json={
                    "story_id": "s-1",
                    "evaluator_id": "ev-1",
                    "scores": {"coherence": 4.5},
                },
            )
        assert resp.status_code == 200
        assert resp.json() == {
            "status": "ok",
            "record": {"story_id": "s-1", "avg": 4.0},
        }
        pipeline.submit_human_eval.assert_called_once_with(
            story_id="s-1", evaluator_id="ev-1", scores_dict={"coherence": 4.5}
        )

    def test_unsafe_story_id_maps_to_400(self):
        with patch("api.eval_routes._pipeline", _patched_pipeline()):
            resp = _client().post(
                "/api/v1/eval/submit",
                json={
                    "story_id": "../etc/passwd",
                    "evaluator_id": "ev-1",
                    "scores": {"coherence": 4.5},
                },
            )
        assert resp.status_code == 400
        assert "story_id" in resp.json()["detail"]

    def test_out_of_range_score_maps_to_422(self):
        resp = _client().post(
            "/api/v1/eval/submit",
            json={"story_id": "s-1", "evaluator_id": "ev-1", "scores": {"x": 9.0}},
        )
        assert resp.status_code == 422

    def test_empty_scores_maps_to_422(self):
        resp = _client().post(
            "/api/v1/eval/submit",
            json={"story_id": "s-1", "evaluator_id": "ev-1", "scores": {}},
        )
        assert resp.status_code == 422


class TestReports:
    def test_golden_eval_returns_pipeline_result(self):
        with patch("api.eval_routes._pipeline", _patched_pipeline()):
            resp = _client().get("/api/v1/eval/golden")
        assert resp.json() == {"status": "pass", "regressions": []}

    def test_report_for_story(self):
        pipeline = _patched_pipeline()
        with patch("api.eval_routes._pipeline", pipeline):
            resp = _client().get("/api/v1/eval/s-1")
        assert resp.json() == {"story_id": "s-1", "aggregate": 4.2}
        pipeline.generate_report.assert_called_once_with(story_id="s-1")

    def test_unsafe_report_id_maps_to_400(self):
        with patch("api.eval_routes._pipeline", _patched_pipeline()):
            resp = _client().get("/api/v1/eval/bad%20id!")
        assert resp.status_code == 400
