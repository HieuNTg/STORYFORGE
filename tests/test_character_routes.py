"""Character endpoint tests — flag gating, rate limit, mocked LLM, parse errors."""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.character_routes import router as character_router
from api import character_routes
from config import ConfigManager


VALID_LLM_PAYLOAD = {
    "name": "Lý Trầm",
    "role": "protagonist",
    "traits": {"strength": 70, "wisdom": 60, "agility": 80, "scheme": 40},
    "description": "Mặt lạnh, đeo kiếm gãy.",
    "backstory": "Mất sư phụ năm 18 tuổi, mang kiếm gãy đi tìm thật tướng.",
    "secret": "Vốn là hậu duệ tà phái.",
    "conflict": "Tha thứ hay báo thù.",
}


@pytest.fixture(autouse=True)
def _reset_state():
    character_routes._character_state.clear()
    cfg = ConfigManager()
    original = getattr(cfg.pipeline, "enable_character_traits", False)
    cfg.pipeline.enable_character_traits = True
    yield
    cfg.pipeline.enable_character_traits = original
    character_routes._character_state.clear()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(character_router, prefix="/api")
    return TestClient(app, raise_server_exceptions=False)


def _mock_llm(payload):
    llm = MagicMock()
    if isinstance(payload, Exception):
        llm.generate.side_effect = payload
    else:
        llm.generate.return_value = (
            payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        )
    return llm


def _req():
    return {
        "name": "Lý Trầm",
        "role": "protagonist",
        "genre": "Tiên Hiệp",
        "extraContext": "Một kiếm khách phế võ công.",
    }


def test_character_happy_path(client):
    with patch.object(character_routes, "_get_llm", return_value=_mock_llm(VALID_LLM_PAYLOAD)):
        resp = client.post("/api/characters/generate", json=_req())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Lý Trầm"
    assert body["role"] == "protagonist"
    assert set(body["traits"].keys()) == {"strength", "wisdom", "agility", "scheme"}
    assert all(0 <= v <= 100 for v in body["traits"].values())


def test_character_returns_404_when_flag_off(client):
    cfg = ConfigManager()
    cfg.pipeline.enable_character_traits = False
    resp = client.post("/api/characters/generate", json=_req())
    assert resp.status_code == 404


def test_character_rejects_empty_name(client):
    with patch.object(character_routes, "_get_llm", return_value=_mock_llm(VALID_LLM_PAYLOAD)):
        bad = _req() | {"name": ""}
        resp = client.post("/api/characters/generate", json=bad)
    assert resp.status_code == 422


def test_character_rejects_invalid_role(client):
    with patch.object(character_routes, "_get_llm", return_value=_mock_llm(VALID_LLM_PAYLOAD)):
        bad = _req() | {"role": "villain"}
        resp = client.post("/api/characters/generate", json=bad)
    assert resp.status_code == 422


def test_character_rate_limit_429(client):
    with patch.object(character_routes, "_get_llm", return_value=_mock_llm(VALID_LLM_PAYLOAD)):
        for _ in range(character_routes.CHARACTER_LIMIT_PER_MIN):
            r = client.post("/api/characters/generate", json=_req())
            assert r.status_code == 200
        r = client.post("/api/characters/generate", json=_req())
        assert r.status_code == 429


def test_character_clamps_traits_out_of_range(client):
    payload = dict(VALID_LLM_PAYLOAD)
    payload["traits"] = {"strength": 250, "wisdom": -10, "agility": 50, "scheme": 50}
    with patch.object(character_routes, "_get_llm", return_value=_mock_llm(payload)):
        resp = client.post("/api/characters/generate", json=_req())
    assert resp.status_code == 200
    body = resp.json()
    assert body["traits"]["strength"] == 100
    assert body["traits"]["wisdom"] == 0


def test_character_retry_then_succeed(client):
    llm = MagicMock()
    llm.generate.side_effect = [
        "not json{{",
        json.dumps(VALID_LLM_PAYLOAD, ensure_ascii=False),
    ]
    with patch.object(character_routes, "_get_llm", return_value=llm):
        resp = client.post("/api/characters/generate", json=_req())
    assert resp.status_code == 200
    assert llm.generate.call_count == 2


def test_character_502_when_both_attempts_fail(client):
    llm = MagicMock()
    llm.generate.side_effect = ["junk", "still junk"]
    with patch.object(character_routes, "_get_llm", return_value=llm):
        resp = client.post("/api/characters/generate", json=_req())
    assert resp.status_code == 502
    assert llm.generate.call_count == 2
    body = resp.json()
    message = (body.get("detail") or body.get("error") or "").lower()
    assert "character generation failed" in message


def test_character_rejects_missing_trait_key(client):
    payload = dict(VALID_LLM_PAYLOAD)
    payload["traits"] = {"strength": 50, "wisdom": 50, "agility": 50}  # missing scheme
    llm = MagicMock()
    llm.generate.side_effect = [
        json.dumps(payload, ensure_ascii=False),
        json.dumps(VALID_LLM_PAYLOAD, ensure_ascii=False),
    ]
    with patch.object(character_routes, "_get_llm", return_value=llm):
        resp = client.post("/api/characters/generate", json=_req())
    assert resp.status_code == 200
    assert llm.generate.call_count == 2


def test_character_forces_name_and_role_from_request(client):
    # LLM tries to drift name/role; service must clamp back.
    payload = dict(VALID_LLM_PAYLOAD)
    payload["name"] = "DriftedName"
    payload["role"] = "rival"
    with patch.object(character_routes, "_get_llm", return_value=_mock_llm(payload)):
        resp = client.post("/api/characters/generate", json=_req())
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Lý Trầm"
    assert body["role"] == "protagonist"
