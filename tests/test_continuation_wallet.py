"""Every continuation entry point that calls the LLM runs inside a cost wallet.

/continue, /continue/write, /continue/paths and /continue/select-path already
went through orchestrator wrappers that open the per-run wallet (caps only
apply inside one). /collaborative-chapter (polish) and /check-consistency
called ``orch.continuation`` directly, outside any wallet, and
/regenerate-chapter and /insert-chapter called orchestrator methods that did
not exist (AttributeError, so the routes never worked). All four now go
through wrappers that open the wallet.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient

from models.schemas import Chapter, ConsistencyReport, PipelineOutput
from tests.test_multipath_preview import _make_draft


def _events(text: str) -> list[dict]:
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


@pytest_asyncio.fixture
async def client():
    from api.continuation_routes import router

    app = FastAPI()
    api = APIRouter(prefix="/api")
    api.include_router(router)
    app.include_router(api)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def checkpoint(tmp_path):
    path = tmp_path / "ckpt.json"
    path.write_text(
        PipelineOutput(story_draft=_make_draft(3), status="done").model_dump_json(),
        encoding="utf-8",
    )
    with (
        patch("api.continuation_routes._resolve_checkpoint", return_value=path),
        patch("api.continuation_routes._backup_checkpoint"),
        patch("pipeline.orchestrator_checkpoint.CheckpointManager.save"),
        patch("services.continuation_history.record_continuation"),
    ):
        yield path


def _record_wallet(seen: dict) -> None:
    from services.llm.client import LLMClient, current_run_id

    rid = current_run_id.get()
    seen["wallet_open"] = bool(rid) and LLMClient.has_wallet(rid)
    seen["run_id"] = rid


def _assert_wallet_was_open_and_closed(seen: dict) -> None:
    from services.llm.client import LLMClient

    assert seen.get("wallet_open") is True, f"LLM work ran outside a wallet: {seen}"
    assert not LLMClient.has_wallet(seen["run_id"]), "wallet must be closed afterwards"


@pytest.mark.asyncio
async def test_polish_runs_inside_a_wallet(client, checkpoint):
    seen: dict = {}

    def _polish(*, generator, draft, chapter_number, **_kw):
        _record_wallet(seen)
        draft.chapters[chapter_number - 1].content = "Polished"
        return draft

    with patch(
        "pipeline.layer1_story.story_continuation.polish_chapter_impl", side_effect=_polish
    ):
        r = await client.post(
            "/api/pipeline/collaborative-chapter",
            json={"checkpoint": "ckpt.json", "chapter_number": 2, "user_text": "x" * 120},
        )
    assert r.status_code == 200
    assert _events(r.text)[-1]["type"] == "done", r.text
    _assert_wallet_was_open_and_closed(seen)


@pytest.mark.asyncio
async def test_check_consistency_runs_inside_a_wallet(client, checkpoint):
    seen: dict = {}

    def _check(self, draft, progress_callback=None):
        _record_wallet(seen)
        return ConsistencyReport(checked_chapters=[1, 2, 3])

    with patch(
        "pipeline.layer1_story.consistency_checker.ConsistencyChecker.check_full_story",
        _check,
    ):
        r = await client.post("/api/pipeline/check-consistency", json={"checkpoint": "ckpt.json"})
    assert r.status_code == 200
    events = _events(r.text)
    assert events[-1]["type"] == "done", r.text
    assert events[-1]["data"]["checked_chapters"] == [1, 2, 3]
    _assert_wallet_was_open_and_closed(seen)


@pytest.mark.asyncio
async def test_regenerate_chapter_runs_inside_a_wallet(client, checkpoint):
    seen: dict = {}

    def _regen(*, generator, draft, chapter_number, **_kw):
        _record_wallet(seen)
        seen["loaded_chapters"] = len(draft.chapters)
        draft.chapters[chapter_number - 1].content = "Regenerated"
        return draft

    with patch(
        "pipeline.layer1_story.story_continuation.regenerate_chapter_impl", side_effect=_regen
    ):
        r = await client.post(
            "/api/pipeline/regenerate-chapter",
            json={"checkpoint": "ckpt.json", "chapter_number": 2},
        )
    assert r.status_code == 200
    assert _events(r.text)[-1]["type"] == "done", r.text
    assert seen["loaded_chapters"] == 3
    _assert_wallet_was_open_and_closed(seen)


@pytest.mark.asyncio
async def test_insert_chapter_runs_inside_a_wallet(client, checkpoint):
    seen: dict = {}

    def _insert(*, generator, draft, insert_after, **_kw):
        _record_wallet(seen)
        draft.chapters.insert(
            insert_after,
            Chapter(chapter_number=insert_after + 1, title="New", content="Inserted", word_count=1),
        )
        return draft

    with patch(
        "pipeline.layer1_story.story_continuation.insert_chapter_impl", side_effect=_insert
    ):
        r = await client.post(
            "/api/pipeline/insert-chapter",
            json={"checkpoint": "ckpt.json", "insert_after": 1},
        )
    assert r.status_code == 200
    assert _events(r.text)[-1]["type"] == "done", r.text
    _assert_wallet_was_open_and_closed(seen)
