"""Forge endpoint tests — flag gating, rate limit, mocked LLM, parse errors."""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.forge_routes import router as forge_router
from api import forge_routes
from config import ConfigManager


VALID_LLM_PAYLOAD = {
    "title": "Bóng Kiếm Trên Tuyết",
    "genre": "Tiên Hiệp",
    "setting": "Đại Sơn Bắc cảnh, cuối thời Tống.",
    "tone": "dark",
    "description": "Một kiếm khách bị phế võ công đi tìm sư phụ đã chết.",
    "characters": [
        {
            "name": "Lý Trầm",
            "role": "protagonist",
            "traits": {"strength": 70, "wisdom": 60, "agility": 80, "scheme": 40},
            "description": "Mặt lạnh, đeo kiếm gãy.",
            "backstory": "Mất sư phụ năm 18 tuổi.",
            "secret": "Vốn là hậu duệ tà phái.",
            "conflict": "Tha thứ hay báo thù.",
        },
        {
            "name": "Vũ Thanh",
            "role": "antagonist",
            "traits": {"strength": 60, "wisdom": 90, "agility": 50, "scheme": 95},
            "description": "Áo trắng, cười nhạt.",
            "backstory": "Sư huynh phản phái.",
            "secret": "Y đã giết sư phụ.",
            "conflict": "Quyền lực hay tình nghĩa.",
        },
    ],
    "firstChapter": {
        "title": "Tuyết Đầu Đông",
        "content": "Tuyết rơi dày trên đỉnh Hoành Sơn. " * 40,
        "summary": "Lý Trầm nhận tin sư phụ chết.",
        "choices": [
            {"id": "a", "label": "Xuống núi điều tra", "actionPrompt": "Tới Trấn Nam"},
            {"id": "b", "label": "Ở lại tu luyện", "actionPrompt": "Bế quan 3 tháng"},
        ],
    },
}


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset in-memory rate limit state + force flag on per test."""
    forge_routes._forge_state.clear()
    cfg = ConfigManager()
    original = getattr(cfg.pipeline, "enable_sentence_forge", False)
    cfg.pipeline.enable_sentence_forge = True
    yield
    cfg.pipeline.enable_sentence_forge = original
    forge_routes._forge_state.clear()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(forge_router, prefix="/api")
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


def test_forge_sync_happy_path(client):
    """200 + valid ForgeResponse when LLM returns clean JSON."""
    with patch.object(
        forge_routes, "_get_llm", return_value=_mock_llm(VALID_LLM_PAYLOAD)
    ):
        resp = client.post(
            "/api/forge/sentence",
            json={"sentenceIdea": "Một kiếm khách bị phế võ công đi tìm sư phụ."},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["title"] == "Bóng Kiếm Trên Tuyết"
    assert len(body["characters"]) == 2
    assert len(body["firstChapter"]["choices"]) == 2
    assert body["firstChapter"]["choices"][0]["id"] == "a"


def test_forge_returns_404_when_flag_off(client):
    """Endpoint hidden behind enable_sentence_forge flag."""
    cfg = ConfigManager()
    cfg.pipeline.enable_sentence_forge = False
    resp = client.post(
        "/api/forge/sentence",
        json={"sentenceIdea": "Một câu ý tưởng nào đó."},
    )
    assert resp.status_code == 404


def test_forge_rejects_short_sentence(client):
    """Pydantic rejects sentence < 10 chars with 422."""
    with patch.object(
        forge_routes, "_get_llm", return_value=_mock_llm(VALID_LLM_PAYLOAD)
    ):
        resp = client.post("/api/forge/sentence", json={"sentenceIdea": "ngắn"})
    assert resp.status_code == 422


def test_forge_rejects_long_sentence(client):
    """Pydantic rejects sentence > 500 chars with 422."""
    with patch.object(
        forge_routes, "_get_llm", return_value=_mock_llm(VALID_LLM_PAYLOAD)
    ):
        resp = client.post("/api/forge/sentence", json={"sentenceIdea": "x" * 501})
    assert resp.status_code == 422


def test_forge_rate_limit_429(client):
    """5/min/IP — 6th request in same window returns 429."""
    with patch.object(
        forge_routes, "_get_llm", return_value=_mock_llm(VALID_LLM_PAYLOAD)
    ):
        sentence = "Một kiếm khách đi tìm sư phụ đã chết."
        for _ in range(forge_routes.FORGE_LIMIT_PER_MIN):
            r = client.post("/api/forge/sentence", json={"sentenceIdea": sentence})
            assert r.status_code == 200
        r = client.post("/api/forge/sentence", json={"sentenceIdea": sentence})
        assert r.status_code == 429


def test_forge_resilient_parse_fenced_json(client):
    """Parser strips ```json fences before validation — succeeds on first try."""
    fenced = "```json\n" + json.dumps(VALID_LLM_PAYLOAD, ensure_ascii=False) + "\n```"
    with patch.object(forge_routes, "_get_llm", return_value=_mock_llm(fenced)):
        resp = client.post(
            "/api/forge/sentence",
            json={"sentenceIdea": "Một kiếm khách bị phế võ công đi tìm sư phụ."},
        )
    assert resp.status_code == 200
    assert resp.json()["title"] == VALID_LLM_PAYLOAD["title"]


def test_forge_retry_then_succeed(client):
    """Bad first response → retry → valid second response → 200."""
    llm = MagicMock()
    llm.generate.side_effect = [
        "not json at all{{{",
        json.dumps(VALID_LLM_PAYLOAD, ensure_ascii=False),
    ]
    with patch.object(forge_routes, "_get_llm", return_value=llm):
        resp = client.post(
            "/api/forge/sentence",
            json={"sentenceIdea": "Một kiếm khách bị phế võ công đi tìm sư phụ."},
        )
    assert resp.status_code == 200
    assert llm.generate.call_count == 2


def test_forge_returns_502_when_both_attempts_fail(client):
    """Both LLM attempts fail → sanitized 502."""
    llm = MagicMock()
    llm.generate.side_effect = ["junk", "still junk"]
    with patch.object(forge_routes, "_get_llm", return_value=llm):
        resp = client.post(
            "/api/forge/sentence",
            json={"sentenceIdea": "Một câu ý tưởng đầy đủ chiều dài."},
        )
    assert resp.status_code == 502
    assert llm.generate.call_count == 2
    body = resp.json()
    # Should NOT leak full stack; only error type name. FastAPI HTTPException → "detail".
    message = (body.get("detail") or body.get("error") or "").lower()
    assert "forge failed" in message


def test_resilient_json_loads_trailing_comma():
    """Direct unit test on parser — trailing commas repaired."""
    from services.forge_service import _resilient_json_loads

    raw = '{"a": 1, "b": [1, 2, 3,],}'
    parsed = _resilient_json_loads(raw)
    assert parsed == {"a": 1, "b": [1, 2, 3]}


def test_resilient_json_loads_prose_wrapped():
    """Extracts first {...} block from prose-wrapped LLM output."""
    from services.forge_service import _resilient_json_loads

    raw = 'Sure, here you go:\n{"a": 1}\nLet me know if you need more.'
    parsed = _resilient_json_loads(raw)
    assert parsed == {"a": 1}
