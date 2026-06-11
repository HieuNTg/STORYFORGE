"""Simulation endpoint tests — flag gating, transcript extract, continue (mocked LLM), rate limit."""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.simulation_routes import router as simulation_router
from api import simulation_routes
from config import ConfigManager


VALID_TURN_PAYLOAD = {
    "senderId": "Lý Trầm",
    "senderName": "Lý Trầm",
    "emotion": "phẫn nộ",
    "actionDetails": "Rút kiếm gãy chỉ vào đối thủ.",
    "speech": "Trả lại sư phụ ta.",
}


@pytest.fixture(autouse=True)
def _reset_state():
    simulation_routes._continue_state.clear()
    cfg = ConfigManager()
    enabled = getattr(cfg.pipeline, "enable_simulation_transcript", False)
    climax = getattr(cfg.pipeline, "enable_drama_climax", False)
    cfg.pipeline.enable_simulation_transcript = True
    cfg.pipeline.enable_drama_climax = True
    yield
    cfg.pipeline.enable_simulation_transcript = enabled
    cfg.pipeline.enable_drama_climax = climax
    simulation_routes._continue_state.clear()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(simulation_router, prefix="/api")
    return TestClient(app, raise_server_exceptions=False)


def _mock_llm(payload):
    llm = MagicMock()
    if isinstance(payload, Exception):
        llm.generate.side_effect = payload
    else:
        llm.generate.return_value = (
            payload
            if isinstance(payload, str)
            else json.dumps(payload, ensure_ascii=False)
        )
    return llm


def _continue_req():
    return {
        "characters": [{"name": "Lý Trầm", "role": "protagonist"}],
        "historyLogs": [],
        "topic": "Đối đầu trong đại điện",
        "dramaLevel": "high",
    }


def test_continue_happy_path(client):
    with patch.object(
        simulation_routes, "_get_llm", return_value=_mock_llm(VALID_TURN_PAYLOAD)
    ):
        resp = client.post("/api/simulation/continue", json=_continue_req())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["senderName"] == "Lý Trầm"
    assert body["speech"]
    assert body["id"].startswith("t-cont-") or len(body["id"]) > 0


def test_continue_404_when_flag_off(client):
    cfg = ConfigManager()
    cfg.pipeline.enable_simulation_transcript = False
    resp = client.post("/api/simulation/continue", json=_continue_req())
    assert resp.status_code == 404


def test_continue_rejects_empty_topic(client):
    bad = _continue_req() | {"topic": ""}
    resp = client.post("/api/simulation/continue", json=bad)
    assert resp.status_code == 422


def test_continue_rejects_empty_characters(client):
    bad = _continue_req() | {"characters": []}
    resp = client.post("/api/simulation/continue", json=bad)
    assert resp.status_code == 422


def test_continue_rate_limit_429(client):
    with patch.object(
        simulation_routes, "_get_llm", return_value=_mock_llm(VALID_TURN_PAYLOAD)
    ):
        for _ in range(simulation_routes.CONTINUE_LIMIT_PER_MIN):
            r = client.post("/api/simulation/continue", json=_continue_req())
            assert r.status_code == 200
        r = client.post("/api/simulation/continue", json=_continue_req())
        assert r.status_code == 429


def test_continue_502_on_bad_llm_output(client):
    with patch.object(
        simulation_routes, "_get_llm", return_value=_mock_llm("totally not json")
    ):
        resp = client.post("/api/simulation/continue", json=_continue_req())
    assert resp.status_code == 502


def test_continue_clamps_unknown_sender_to_known_char(client):
    drifted = dict(VALID_TURN_PAYLOAD)
    drifted["senderName"] = "Unknown Drift"
    drifted["senderId"] = "Unknown Drift"
    with patch.object(simulation_routes, "_get_llm", return_value=_mock_llm(drifted)):
        resp = client.post("/api/simulation/continue", json=_continue_req())
    assert resp.status_code == 200
    body = resp.json()
    assert body["senderName"] == "Lý Trầm"


def test_transcript_404_when_session_missing(client):
    resp = client.get("/api/simulation/nonexistent/transcript")
    assert resp.status_code == 404


def test_transcript_extracts_from_session_artifact(client):
    from models.schemas import AgentPost, SimulationResult

    artifact = SimulationResult(
        agent_posts=[
            AgentPost(
                round_number=1,
                agent_name="Lý Trầm",
                content="Trả lại sư phụ ta!",
                sentiment="phẫn nộ",
                action_type="speech",
            ),
            AgentPost(
                round_number=1,
                agent_name="Vô Danh",
                content="Ngươi không hiểu gì cả.",
                sentiment="lạnh lùng",
                action_type="speech",
            ),
        ],
        drama_suggestions=["Tăng kịch tính cảnh đối đầu", "Thêm tiết lộ về sư phụ"],
    )

    class _FakeOutput:
        simulation_result = artifact

    class _FakeOrch:
        output = _FakeOutput()

    with patch.object(
        simulation_routes,
        "_lookup_session_artifact",
        return_value=artifact,
    ):
        resp = client.get("/api/simulation/sess-123/transcript")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["logs"]) == 2
    assert body["logs"][0]["senderName"] == "Lý Trầm"
    assert body["logs"][0]["emotion"] == "phẫn nộ"
    assert "kịch tính" in body["outcomeSummary"]
