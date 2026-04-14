"""Coverage tests for dashboard API routes."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False


def _make_client():
    # Reset cached HTML so tests are isolated
    import api.dashboard_routes as dr
    dr._DASHBOARD_CACHE = None
    from api.dashboard_routes import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.skipif(not _HAS_FASTAPI, reason="FastAPI not installed")
class TestDashboardSummary:
    """GET /dashboard/summary endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.client = _make_client()

    def test_summary_returns_200(self):
        with patch("services.metrics.format_metrics", return_value=""):
            resp = self.client.get("/dashboard/summary")
        assert resp.status_code == 200

    def test_summary_has_required_keys(self):
        with patch("services.metrics.format_metrics", return_value=""):
            resp = self.client.get("/dashboard/summary")
        data = resp.json()
        assert "pipeline" in data
        assert "llm" in data
        assert "quality" in data
        assert "timestamp" in data

    def test_summary_pipeline_counts_from_metrics(self):
        prom_text = (
            'pipeline_runs_total{status="success"} 10\n'
            'pipeline_runs_total{status="error"} 2\n'
            "active_pipelines 1\n"
        )
        with patch("services.metrics.format_metrics", return_value=prom_text):
            resp = self.client.get("/dashboard/summary")
        data = resp.json()
        assert data["pipeline"]["success"] == 10
        assert data["pipeline"]["error"] == 2
        assert data["pipeline"]["total"] == 12
        assert data["pipeline"]["active"] == 1

    def test_summary_llm_counts(self):
        prom_text = (
            'llm_requests_total{model="gpt4"} 50\n'
            'llm_errors_total{model="gpt4"} 3\n'
        )
        with patch("services.metrics.format_metrics", return_value=prom_text):
            resp = self.client.get("/dashboard/summary")
        data = resp.json()
        assert data["llm"]["total_requests"] == 50
        assert data["llm"]["total_errors"] == 3

    def test_summary_empty_metrics(self):
        with patch("services.metrics.format_metrics", return_value=""):
            resp = self.client.get("/dashboard/summary")
        data = resp.json()
        assert data["pipeline"]["total"] == 0
        assert data["llm"]["total_requests"] == 0

    def test_summary_with_comments_and_blank_lines(self):
        prom_text = (
            "# HELP pipeline_runs_total Total pipeline runs\n"
            "# TYPE pipeline_runs_total counter\n"
            "\n"
            'pipeline_runs_total{status="success"} 5\n'
        )
        with patch("services.metrics.format_metrics", return_value=prom_text):
            resp = self.client.get("/dashboard/summary")
        data = resp.json()
        assert data["pipeline"]["success"] == 5


@pytest.mark.skipif(not _HAS_FASTAPI, reason="FastAPI not installed")
class TestDashboardTestTimings:
    """GET /dashboard/test-timings endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.client = _make_client()

    def test_timings_no_file_returns_empty(self):
        import api.dashboard_routes as dr
        orig = dr._TIMINGS_PATH
        dr._TIMINGS_PATH = Path("/nonexistent/timings.json")
        try:
            resp = self.client.get("/dashboard/test-timings")
        finally:
            dr._TIMINGS_PATH = orig
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["timestamp"] is None

    def test_timings_with_data(self):
        import api.dashboard_routes as dr
        sample = {
            "timestamp": 1000.0,
            "total_duration": 60.0,
            "tests": [
                {"name": "test_foo", "duration": 1.5, "status": "passed"},
                {"name": "test_bar", "duration": 0.5, "status": "failed"},
            ],
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(sample, f)
            tmp_path = Path(f.name)
        orig = dr._TIMINGS_PATH
        dr._TIMINGS_PATH = tmp_path
        try:
            resp = self.client.get("/dashboard/test-timings")
        finally:
            dr._TIMINGS_PATH = orig
            tmp_path.unlink(missing_ok=True)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        assert data["timestamp"] == 1000.0

    def test_timings_pagination(self):
        import api.dashboard_routes as dr
        tests = [{"name": f"test_{i}", "duration": float(i), "status": "passed"} for i in range(10)]
        sample = {"timestamp": 1.0, "total_duration": 10.0, "tests": tests}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(sample, f)
            tmp_path = Path(f.name)
        orig = dr._TIMINGS_PATH
        dr._TIMINGS_PATH = tmp_path
        try:
            resp = self.client.get("/dashboard/test-timings?limit=3&offset=2")
        finally:
            dr._TIMINGS_PATH = orig
            tmp_path.unlink(missing_ok=True)
        data = resp.json()
        assert data["limit"] == 3
        assert data["offset"] == 2
        assert len(data["items"]) == 3
        assert data["total"] == 10

    def test_timings_invalid_json_returns_empty(self):
        import api.dashboard_routes as dr
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            f.write("not valid json {{{")
            tmp_path = Path(f.name)
        orig = dr._TIMINGS_PATH
        dr._TIMINGS_PATH = tmp_path
        try:
            resp = self.client.get("/dashboard/test-timings")
        finally:
            dr._TIMINGS_PATH = orig
            tmp_path.unlink(missing_ok=True)
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []


@pytest.mark.skipif(not _HAS_FASTAPI, reason="FastAPI not installed")
class TestDashboardHTML:
    """GET /dashboard — serves HTML page."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.client = _make_client()

    def test_serve_dashboard_returns_html(self):
        import api.dashboard_routes as dr
        orig_path = dr._DASHBOARD_PATH
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write("<html><body>Dashboard</body></html>")
            tmp_path = Path(f.name)
        dr._DASHBOARD_CACHE = None
        dr._DASHBOARD_PATH = tmp_path
        try:
            resp = self.client.get("/dashboard")
        finally:
            dr._DASHBOARD_PATH = orig_path
            dr._DASHBOARD_CACHE = None
            tmp_path.unlink(missing_ok=True)
        assert resp.status_code == 200
        assert "Dashboard" in resp.text

    def test_serve_dashboard_caches_html(self):
        """Second request uses cached content."""
        import api.dashboard_routes as dr
        dr._DASHBOARD_CACHE = "<html>Cached</html>"
        try:
            resp = self.client.get("/dashboard")
        finally:
            dr._DASHBOARD_CACHE = None
        assert resp.status_code == 200
        assert "Cached" in resp.text


@pytest.mark.skipif(not _HAS_FASTAPI, reason="FastAPI not installed")
class TestParsePrometheus:
    """_parse_prometheus helper directly."""

    def test_plain_metric(self):
        from api.dashboard_routes import _parse_prometheus
        result = _parse_prometheus("active_pipelines 3\n")
        assert result["active_pipelines"] == 3.0

    def test_labeled_metric(self):
        from api.dashboard_routes import _parse_prometheus
        result = _parse_prometheus('pipeline_runs_total{status="success"} 7\n')
        assert result['pipeline_runs_total{status="success"}'] == 7.0

    def test_skips_comments_and_blanks(self):
        from api.dashboard_routes import _parse_prometheus
        text = "# comment\n\nactive_pipelines 1\n"
        result = _parse_prometheus(text)
        assert "active_pipelines" in result
        assert len(result) == 1

    def test_scientific_notation(self):
        from api.dashboard_routes import _parse_prometheus
        result = _parse_prometheus("some_metric 1.5e+2\n")
        assert result["some_metric"] == pytest.approx(150.0)
