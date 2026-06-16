"""Route tests for api/metrics_routes.py (previously untested).

Both endpoints return Prometheus text format; the formatters are patched
in the route module / on the metrics singleton for determinism.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client() -> TestClient:
    app = FastAPI()
    from api.metrics_routes import router

    app.include_router(router, prefix="/api")
    return TestClient(app)


def test_metrics_returns_prometheus_text():
    with patch(
        "api.metrics_routes.format_metrics",
        return_value='requests_total{path="/api"} 3\n',
    ):
        resp = _client().get("/api/metrics")
    assert resp.status_code == 200
    assert resp.text == 'requests_total{path="/api"} 3\n'
    assert resp.headers["content-type"].startswith("text/plain; version=0.0.4")


def test_prometheus_metrics_endpoint_uses_singleton_formatter():
    with patch("api.metrics_routes.prometheus_metrics") as metrics:
        metrics.format_prometheus.return_value = "storyforge_uptime_seconds 12\n"
        resp = _client().get("/api/metrics/prometheus")
    assert resp.status_code == 200
    assert resp.text == "storyforge_uptime_seconds 12\n"
    assert resp.headers["content-type"].startswith("text/plain; version=0.0.4")
