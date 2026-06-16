"""Route tests for api/prompt_routes.py (previously untested).

Prompt-registry functions and the A/B bridge are imported at module top, so
they are patched in the route module's namespace; prompt_manager is lazily
imported inside handlers, so it is patched at its source module.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client() -> TestClient:
    app = FastAPI()
    from api.prompt_routes import router

    app.include_router(router, prefix="/api")
    return TestClient(app)


class TestRegistryRoutes:
    def test_current_version(self):
        with patch(
            "api.prompt_routes.get_prompt_version",
            return_value={"version": "v2", "file": "prompts_v2.yaml"},
        ):
            resp = _client().get("/api/prompts/version")
        assert resp.json() == {"version": "v2", "file": "prompts_v2.yaml"}

    def test_all_versions(self):
        with patch("api.prompt_routes.list_prompt_versions", return_value=["v1", "v2"]):
            resp = _client().get("/api/prompts/versions")
        assert resp.json() == {"versions": ["v1", "v2"]}

    def test_active_prompts_returns_count_and_keys(self):
        with patch(
            "api.prompt_routes.get_active_prompts",
            return_value={"outline": "...", "chapter": "..."},
        ):
            resp = _client().get("/api/prompts/active")
        body = resp.json()
        assert body["prompt_count"] == 2
        assert sorted(body["prompts"]) == ["chapter", "outline"]

    def test_diff_versions_forwards_params(self):
        with patch(
            "api.prompt_routes.get_prompt_diff", return_value={"added": ["x"]}
        ) as mock_diff:
            resp = _client().get("/api/prompts/diff?a=v1&b=v2")
        assert resp.json() == {"added": ["x"]}
        mock_diff.assert_called_once_with("v1", "v2")


class TestPromptManagerRoutes:
    def test_list_prompts(self):
        mgr = MagicMock()
        mgr.list_prompts.return_value = [{"name": "outline", "version": 3}]
        with patch("services.prompt_manager.prompt_manager", mgr):
            resp = _client().get("/api/prompts")
        assert resp.json() == {"prompts": [{"name": "outline", "version": 3}]}

    def test_get_prompt_raw_template(self):
        mgr = MagicMock()
        mgr.get_raw.return_value = "Viết chương {genre}"
        with patch("services.prompt_manager.prompt_manager", mgr):
            resp = _client().get("/api/prompts/outline")
        assert resp.json() == {"name": "outline", "template": "Viết chương {genre}"}

    def test_unknown_prompt_maps_to_404(self):
        mgr = MagicMock()
        mgr.get_raw.side_effect = KeyError("outline-x")
        with patch("services.prompt_manager.prompt_manager", mgr):
            resp = _client().get("/api/prompts/outline-x")
        assert resp.status_code == 404

    def test_preview_formats_with_genre(self):
        mgr = MagicMock()
        mgr.get.return_value = "Prompt đã định dạng"
        with patch("services.prompt_manager.prompt_manager", mgr):
            resp = _client().get("/api/prompts/outline/preview?genre=Kiếm%20Hiệp")
        body = resp.json()
        assert body == {
            "name": "outline",
            "genre": "Kiếm Hiệp",
            "preview": "Prompt đã định dạng",
        }
        mgr.get.assert_called_once_with("outline", genre="Kiếm Hiệp")

    def test_preview_forwards_extra_query_params_as_template_vars(self):
        mgr = MagicMock()
        mgr.get.return_value = "ok"
        with patch("services.prompt_manager.prompt_manager", mgr):
            resp = _client().get(
                "/api/prompts/outline/preview?genre=Tiên%20Hiệp&hero=Lan%20Anh"
            )
        assert resp.status_code == 200
        mgr.get.assert_called_once_with("outline", genre="Tiên Hiệp", hero="Lan Anh")

    def test_preview_format_error_maps_to_400(self):
        mgr = MagicMock()
        mgr.get.side_effect = RuntimeError("thiếu biến template")
        with patch("services.prompt_manager.prompt_manager", mgr):
            resp = _client().get("/api/prompts/outline/preview")
        assert resp.status_code == 400


class TestExperimentRoutes:
    def test_list_experiments(self):
        bridge = MagicMock()
        bridge.list_active_experiments.return_value = [{"prompt": "outline"}]
        with patch("api.prompt_routes.bridge", bridge):
            resp = _client().get("/api/prompts/experiments")
        assert resp.json() == {"experiments": [{"prompt": "outline"}]}

    def test_experiment_results_unknown_maps_to_404(self):
        bridge = MagicMock()
        bridge.get_experiment_results.side_effect = KeyError("outline")
        with patch("api.prompt_routes.bridge", bridge):
            resp = _client().get("/api/prompts/experiments/outline/results")
        assert resp.status_code == 404

    def test_create_experiment(self):
        bridge = MagicMock()
        bridge.create_prompt_experiment.return_value = "exp-9"
        with patch("api.prompt_routes.bridge", bridge):
            resp = _client().post(
                "/api/prompts/experiments",
                json={"prompt_name": "outline", "variants": ["v1", "v2"]},
            )
        assert resp.status_code == 201
        assert resp.json() == {"experiment_id": "exp-9", "prompt_name": "outline"}

    def test_create_experiment_value_error_maps_to_400(self):
        bridge = MagicMock()
        bridge.create_prompt_experiment.side_effect = ValueError("biến thể trùng")
        with patch("api.prompt_routes.bridge", bridge):
            resp = _client().post(
                "/api/prompts/experiments",
                json={"prompt_name": "outline", "variants": ["v1", "v1"]},
            )
        assert resp.status_code == 400
