"""Route tests for api/ab_routes.py (previously untested).

The module-level ab_testing manager singleton is patched so tests stay
hermetic; the auth dependency is overridden per-app.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from middleware.auth_middleware import get_current_user


def _client() -> TestClient:
    app = FastAPI()
    from api.ab_routes import router

    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "u1",
        "username": "tester",
        "role": "creator",
    }
    return TestClient(app)


class TestCreateExperiment:
    def test_create_returns_experiment_id(self):
        mgr = MagicMock()
        mgr.create_experiment.return_value = "exp-1"
        with patch("api.ab_routes.manager", mgr):
            resp = _client().post(
                "/api/ab/experiments",
                json={"name": "tiêu đề chương", "variants": ["a", "b"]},
            )
        assert resp.status_code == 201
        assert resp.json() == {"experiment_id": "exp-1"}
        mgr.create_experiment.assert_called_once_with("tiêu đề chương", ["a", "b"])

    def test_duplicate_name_maps_to_400(self):
        mgr = MagicMock()
        mgr.create_experiment.side_effect = ValueError("trùng tên")
        with patch("api.ab_routes.manager", mgr):
            resp = _client().post(
                "/api/ab/experiments",
                json={"name": "x", "variants": ["a", "b"]},
            )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "trùng tên"

    def test_requires_auth(self):
        app = FastAPI()
        from api.ab_routes import router

        app.include_router(router, prefix="/api")
        resp = TestClient(app).post(
            "/api/ab/experiments", json={"name": "x", "variants": ["a", "b"]}
        )
        assert resp.status_code == 401


class TestAssignAndResults:
    def test_list_experiments(self):
        mgr = MagicMock()
        mgr.list_experiments.return_value = [{"id": "exp-1"}]
        with patch("api.ab_routes.manager", mgr):
            resp = _client().get("/api/ab/experiments")
        assert resp.json() == {"experiments": [{"id": "exp-1"}]}

    def test_assign_variant(self):
        mgr = MagicMock()
        mgr.assign_variant.return_value = "b"
        with patch("api.ab_routes.manager", mgr):
            resp = _client().post(
                "/api/ab/experiments/exp-1/assign", json={"session_id": "s1"}
            )
        assert resp.json() == {"variant": "b"}
        mgr.assign_variant.assert_called_once_with("exp-1", "s1")

    def test_assign_unknown_experiment_maps_to_404(self):
        mgr = MagicMock()
        mgr.assign_variant.side_effect = KeyError("exp-x")
        with patch("api.ab_routes.manager", mgr):
            resp = _client().post(
                "/api/ab/experiments/exp-x/assign", json={"session_id": "s1"}
            )
        assert resp.status_code == 404

    def test_record_result(self):
        mgr = MagicMock()
        with patch("api.ab_routes.manager", mgr):
            resp = _client().post(
                "/api/ab/experiments/exp-1/result",
                json={"session_id": "s1", "metric": "ctr", "value": 0.4},
            )
        assert resp.status_code == 201
        mgr.record_result.assert_called_once_with("exp-1", "s1", "ctr", 0.4)

    def test_get_results_unknown_experiment_maps_to_404(self):
        mgr = MagicMock()
        mgr.get_results.side_effect = KeyError("exp-x")
        with patch("api.ab_routes.manager", mgr):
            resp = _client().get("/api/ab/experiments/exp-x/results")
        assert resp.status_code == 404
