"""Library → real continuation pipeline bridge.

Covers the hydration layer (`services/library_continuation.py`), the
`POST /api/pipeline/continue/library` route, and the orchestrator wiring that
`/pipeline/continue` needs in order to run at all.
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.schemas import Chapter, MacroArc, PipelineOutput, StoryDraft
from services.library_continuation import (
    LibraryStoryPayload,
    _checkpoint_basename,
    enhance_tail,
    hydrate_output,
    new_chapters_response,
    payload_to_draft,
    resolve_story_checkpoint,
)


def _payload(**overrides) -> LibraryStoryPayload:
    data = {
        "title": "Vô Gia Vạn Hồn Phả",
        "genre": "Tiên Hiệp",
        "setting": "Bắc Vực, mạt pháp thời đại",
        "tone": "bi tráng",
        "description": "Một thiếu niên gánh vạn hồn đi tìm cố hương.",
        "targetChapters": 150,
        "characters": [
            {
                "name": "Lý Trầm",
                "role": "protagonist",
                "description": "Trầm mặc, quyết đoán.",
                "backstory": "Mồ côi từ nhỏ.",
                "secret": "Trong người có ma hồn.",
                "conflict": "Cứu người hay giữ mình.",
            }
        ],
        "chapters": [
            {
                "title": "Chương 1",
                "content": "Nội dung chương một. " * 20,
                "summary": "Lý Trầm rời làng.",
            },
            {
                "title": "Chương 2",
                "content": "Nội dung chương hai. " * 20,
                "summary": "Gặp lão nhân bí ẩn.",
            },
        ],
    }
    data.update(overrides)
    return LibraryStoryPayload(**data)


# ── Hydration from payload ────────────────────────────────────────────────


def test_payload_to_draft_maps_story_context():
    draft = payload_to_draft(_payload())
    assert draft.title == "Vô Gia Vạn Hồn Phả"
    assert draft.genre == "Tiên Hiệp"
    assert draft.synopsis.startswith("Một thiếu niên")
    assert draft.target_total_chapters == 150
    assert [c.chapter_number for c in draft.chapters] == [1, 2]
    assert draft.world is not None
    assert draft.world.name == "Bắc Vực, mạt pháp thời đại"


def test_payload_to_draft_keeps_character_depth():
    """The old forge path passed only names; the draft must carry the rest."""
    draft = payload_to_draft(_payload())
    char = draft.characters[0]
    assert char.name == "Lý Trầm"
    assert char.personality == "Trầm mặc, quyết đoán."
    assert "Mồ côi từ nhỏ." in char.background
    assert "Trong người có ma hồn." in char.background  # secret folded in
    assert char.internal_conflict == "Cứu người hay giữ mình."


def test_payload_to_draft_synthesises_missing_summary():
    """`rebuild_context` loses context on empty summaries — never ship one."""
    payload = _payload(
        chapters=[{"title": "Ch1", "content": "Câu mở đầu. " * 100, "summary": ""}]
    )
    draft = payload_to_draft(payload)
    assert draft.chapters[0].summary
    assert len(draft.chapters[0].summary) <= 420


def test_payload_to_draft_skips_unnamed_characters():
    draft = payload_to_draft(_payload(characters=[{"name": "", "role": "supporting"}]))
    assert draft.characters == []


# ── Hydration from checkpoint ─────────────────────────────────────────────


def _write_checkpoint(tmp_path, title: str, chapters: int, layer: int = 1) -> str:
    draft = StoryDraft(
        title=title,
        genre="Tiên Hiệp",
        synopsis="Bản gốc từ pipeline.",
        macro_arcs=[
            MacroArc(
                arc_number=1,
                name="Khởi đầu",
                chapter_start=1,
                chapter_end=10,
                central_conflict="Rời làng hay ở lại",
            )
        ],
        chapters=[
            Chapter(
                chapter_number=i + 1,
                title=f"Chương {i + 1}",
                content=f"Bản checkpoint {i + 1}. " * 10,
                summary=f"Tóm tắt {i + 1}",
            )
            for i in range(chapters)
        ],
    )
    path = tmp_path / _checkpoint_basename(title, layer)
    path.write_text(
        PipelineOutput(story_draft=draft).model_dump_json(), encoding="utf-8"
    )
    return str(path)


def test_resolve_story_checkpoint_prefers_layer2(tmp_path):
    title = "Vô Gia Vạn Hồn Phả"
    l1 = _write_checkpoint(tmp_path, title, 2, layer=1)
    l2 = _write_checkpoint(tmp_path, title, 2, layer=2)

    def _find(name):
        cand = tmp_path / name
        return str(cand) if cand.is_file() else None

    with patch("pipeline.orchestrator_checkpoint.find_checkpoint_path", _find):
        assert resolve_story_checkpoint(title) == l2
        os.remove(l2)
        assert resolve_story_checkpoint(title) == l1


def test_hydrate_prefers_checkpoint_and_keeps_planning_signals(tmp_path):
    """Pipeline-born stories must continue with their L1 signals, not a re-invention."""
    title = "Vô Gia Vạn Hồn Phả"
    _write_checkpoint(tmp_path, title, 2)

    def _find(name):
        cand = tmp_path / name
        return str(cand) if cand.is_file() else None

    with patch("pipeline.orchestrator_checkpoint.find_checkpoint_path", _find):
        output, source = hydrate_output(_payload())

    assert source == "checkpoint"
    assert output.story_draft.macro_arcs  # would be empty under payload hydration
    assert output.story_draft.target_total_chapters == 150


def test_hydrate_grafts_client_chapters_beyond_checkpoint(tmp_path):
    """Chapters added client-side after the checkpoint must not be lost."""
    title = "Vô Gia Vạn Hồn Phả"
    _write_checkpoint(tmp_path, title, 2)
    payload = _payload(
        chapters=[
            {"title": "Chương 1", "content": "A " * 20, "summary": "s1"},
            {"title": "Chương 2", "content": "B " * 20, "summary": "s2"},
            {"title": "Chương 3", "content": "C " * 20, "summary": "s3"},
        ]
    )

    def _find(name):
        cand = tmp_path / name
        return str(cand) if cand.is_file() else None

    with patch("pipeline.orchestrator_checkpoint.find_checkpoint_path", _find):
        output, source = hydrate_output(payload)

    draft = output.story_draft
    assert source == "checkpoint"
    assert len(draft.chapters) == 3
    assert draft.chapters[2].content.startswith("C")
    # Client prose wins for chapters the checkpoint also had.
    assert draft.chapters[0].content.startswith("A")


def test_hydrate_never_truncates_a_longer_checkpoint(tmp_path):
    """A stale client must not delete server-side chapters."""
    title = "Vô Gia Vạn Hồn Phả"
    _write_checkpoint(tmp_path, title, 5)
    payload = _payload(
        chapters=[{"title": "Chương 1", "content": "A " * 20, "summary": "s1"}]
    )

    def _find(name):
        cand = tmp_path / name
        return str(cand) if cand.is_file() else None

    with patch("pipeline.orchestrator_checkpoint.find_checkpoint_path", _find):
        output, _ = hydrate_output(payload)

    assert len(output.story_draft.chapters) == 5


def test_hydrate_falls_back_to_payload_without_checkpoint():
    with patch("pipeline.orchestrator_checkpoint.find_checkpoint_path", lambda n: None):
        output, source = hydrate_output(_payload())
    assert source == "payload"
    assert len(output.story_draft.chapters) == 2


def test_hydrate_falls_back_when_checkpoint_is_corrupt(tmp_path):
    title = "Vô Gia Vạn Hồn Phả"
    bad = tmp_path / _checkpoint_basename(title, 1)
    bad.write_text("{not json", encoding="utf-8")

    def _find(name):
        cand = tmp_path / name
        return str(cand) if cand.is_file() else None

    with patch("pipeline.orchestrator_checkpoint.find_checkpoint_path", _find):
        output, source = hydrate_output(_payload())

    assert source == "payload"
    assert len(output.story_draft.chapters) == 2


# ── Response shaping + L2 tail ────────────────────────────────────────────


def test_new_chapters_response_returns_only_the_tail():
    draft = payload_to_draft(_payload())
    draft.chapters.append(
        Chapter(chapter_number=3, title="Chương 3", content="Mới. " * 10, summary="s3")
    )
    out = new_chapters_response(draft, previous_count=2)
    assert [c["number"] for c in out] == [3]
    assert out[0]["title"] == "Chương 3"


def test_enhance_tail_only_touches_new_chapters():
    draft = payload_to_draft(_payload())
    original_first = draft.chapters[0].content
    draft.chapters.append(
        Chapter(chapter_number=3, title="Chương 3", content="Thô. " * 10, summary="s3")
    )

    continuation = MagicMock()
    continuation.analyzer.analyze.return_value = {"relationships": []}
    continuation.enhancer.enhance_with_feedback.return_value = MagicMock(
        chapters=[
            Chapter(
                chapter_number=3,
                title="Chương 3",
                content="Đã tăng cường.",
                summary="s3",
            )
        ]
    )

    merged = enhance_tail(continuation, draft, previous_count=2)

    assert merged == 1
    assert draft.chapters[2].content == "Đã tăng cường."
    assert draft.chapters[0].content == original_first
    # L2 saw only the tail, with the full cast for context.
    sub = continuation.enhancer.enhance_with_feedback.call_args.kwargs["draft"]
    assert [c.chapter_number for c in sub.chapters] == [3]
    assert sub.characters


def test_enhance_tail_survives_l2_crash():
    """L2 is an enhancement, not a gate — a simulator crash must not lose the
    L1 chapters (they are already written and checkpointed)."""
    draft = payload_to_draft(_payload())
    draft.chapters.append(
        Chapter(chapter_number=3, title="Chương 3", content="Thô. " * 10, summary="s3")
    )
    continuation = MagicMock()
    continuation.analyzer.analyze.side_effect = AttributeError(
        "'str' object has no attribute 'get'"
    )

    assert enhance_tail(continuation, draft, previous_count=2) == 0
    assert len(draft.chapters) == 3
    assert draft.chapters[2].content.startswith("Thô.")


def test_enhance_tail_keeps_l1_prose_when_l2_returns_nothing():
    draft = payload_to_draft(_payload())
    draft.chapters.append(
        Chapter(chapter_number=3, title="Chương 3", content="Thô. " * 10, summary="s3")
    )
    continuation = MagicMock()
    continuation.analyzer.analyze.return_value = {"relationships": []}
    continuation.enhancer.enhance_with_feedback.return_value = None

    assert enhance_tail(continuation, draft, previous_count=2) == 0
    assert draft.chapters[2].content.startswith("Thô.")


# ── Orchestrator wiring (this was broken on master) ───────────────────────


def test_orchestrator_continue_story_accepts_arc_directives_and_direction():
    """`/pipeline/continue` passed arc_directives down a signature that didn't
    accept it — an unconditional TypeError on every call."""
    from pipeline.orchestrator import PipelineOrchestrator

    orch = PipelineOrchestrator()
    orch.output = PipelineOutput(story_draft=payload_to_draft(_payload()))
    orch._sync_output()

    captured = {}

    def _fake_continue(**kwargs):
        captured.update(kwargs)
        return kwargs["draft"]

    orch.continuation.story_gen = MagicMock()
    orch.continuation.story_gen.continue_story.side_effect = _fake_continue
    orch.continuation.checkpoint_manager = MagicMock()

    orch.continue_story(
        additional_chapters=2,
        arc_directives=[],
        direction="Cho nhân vật chính gặp phản diện",
    )

    assert captured["additional_chapters"] == 2
    assert captured["direction"] == "Cho nhân vật chính gặp phản diện"
    assert captured["arc_directives"] == []


# ── Route ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolate_sessions():
    """`api.pipeline_routes._sessions` is module-global and capped per IP.

    Continuation endpoints register into it, so leaving entries behind makes
    unrelated tests later in the same process fail with "Too many concurrent
    sessions".
    """
    from api import pipeline_routes

    pipeline_routes._sessions.clear()
    yield
    pipeline_routes._sessions.clear()


@pytest.fixture
def client():
    from api.continuation_routes import router as continuation_router

    app = FastAPI()
    app.include_router(continuation_router, prefix="/api")
    return TestClient(app, raise_server_exceptions=False)


def _sse_events(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


def _post_continue(client, **body_overrides):
    body = {
        "story": _payload().model_dump(),
        "additional_chapters": 1,
        "run_enhancement": False,
    }
    body.update(body_overrides)
    return client.post("/api/pipeline/continue/library", json=body)


def test_continue_library_streams_new_chapters(client):
    """Happy path: the client gets back only the freshly written chapters."""

    def _fake_continue(self, **kwargs):
        draft = self.output.story_draft
        draft.chapters.append(
            Chapter(
                chapter_number=len(draft.chapters) + 1,
                title="Chương 3",
                content="Chương mới do pipeline viết. " * 5,
                summary="Tóm tắt 3",
            )
        )
        return draft

    with (
        patch("pipeline.orchestrator_checkpoint.find_checkpoint_path", lambda n: None),
        patch(
            "pipeline.orchestrator.PipelineOrchestrator.continue_story", _fake_continue
        ),
    ):
        resp = _post_continue(client)

    assert resp.status_code == 200
    events = _sse_events(resp.text)
    done = [e for e in events if e.get("type") == "done"]
    assert done, f"no done event: {events}"
    data = done[0]["data"]
    assert data["hydration_source"] == "payload"
    assert data["total_chapters"] == 3
    assert [c["number"] for c in data["new_chapters"]] == [3]
    assert data["new_chapters"][0]["title"] == "Chương 3"


def test_continue_library_forwards_direction(client):
    """The user's 'Hướng viết tiếp' must reach the outline planner."""
    captured = {}

    def _fake_continue(self, **kwargs):
        captured.update(kwargs)
        draft = self.output.story_draft
        draft.chapters.append(
            Chapter(chapter_number=3, title="C3", content="x " * 20, summary="s")
        )
        return draft

    with (
        patch("pipeline.orchestrator_checkpoint.find_checkpoint_path", lambda n: None),
        patch(
            "pipeline.orchestrator.PipelineOrchestrator.continue_story", _fake_continue
        ),
    ):
        resp = _post_continue(client, direction="Hé lộ bí mật của Lý Trầm")

    assert resp.status_code == 200
    assert captured["direction"] == "Hé lộ bí mật của Lý Trầm"


def test_continue_library_clamps_to_target_chapters(client):
    """Asking for more than the remaining arc writes only what's left."""
    captured = {}
    payload = _payload(targetChapters=3).model_dump()

    def _fake_continue(self, **kwargs):
        captured.update(kwargs)
        draft = self.output.story_draft
        draft.chapters.append(
            Chapter(chapter_number=3, title="C3", content="x " * 20, summary="s")
        )
        return draft

    with (
        patch("pipeline.orchestrator_checkpoint.find_checkpoint_path", lambda n: None),
        patch(
            "pipeline.orchestrator.PipelineOrchestrator.continue_story", _fake_continue
        ),
    ):
        resp = _post_continue(client, story=payload, additional_chapters=10)

    assert resp.status_code == 200
    assert captured["additional_chapters"] == 1


def test_continue_library_errors_when_target_reached(client):
    payload = _payload(targetChapters=2).model_dump()
    with patch("pipeline.orchestrator_checkpoint.find_checkpoint_path", lambda n: None):
        resp = _post_continue(client, story=payload)

    events = _sse_events(resp.text)
    assert any(e.get("type") == "error" for e in events)


def test_continue_library_rejects_empty_story(client):
    payload = _payload(chapters=[]).model_dump()
    resp = _post_continue(client, story=payload)
    events = _sse_events(resp.text)
    assert any(e.get("type") == "error" for e in events)


def test_continue_library_runs_l2_over_new_chapters_only(client):
    """`run_enhancement` must enhance the tail, not the whole story."""
    seen = {}

    def _fake_continue(self, **kwargs):
        draft = self.output.story_draft
        draft.chapters.append(
            Chapter(
                chapter_number=3, title="C3", content="L1 prose. " * 10, summary="s"
            )
        )
        return draft

    def _fake_enhance(continuation, draft, previous_count, **kwargs):
        seen["previous_count"] = previous_count
        seen["total"] = len(draft.chapters)
        draft.chapters[previous_count].content = "L2 prose."
        return 1

    with (
        patch("pipeline.orchestrator_checkpoint.find_checkpoint_path", lambda n: None),
        patch(
            "pipeline.orchestrator.PipelineOrchestrator.continue_story", _fake_continue
        ),
        patch("api.continuation_routes.enhance_tail", _fake_enhance),
        patch(
            "pipeline.orchestrator.PipelineOrchestrator.save_checkpoint",
            lambda self, layer: "",
        ),
    ):
        resp = _post_continue(client, run_enhancement=True)

    assert resp.status_code == 200
    data = [e for e in _sse_events(resp.text) if e.get("type") == "done"][0]["data"]
    # L2 saw the boundary between existing and new chapters.
    assert seen == {"previous_count": 2, "total": 3}
    assert data["enhanced_chapters"] == 1
    assert data["new_chapters"][0]["content"] == "L2 prose."


def test_continue_library_still_returns_chapters_when_l2_yields_nothing(client):
    """A skipped/failed L2 pass must not cost the user their L1 chapter."""

    def _fake_continue(self, **kwargs):
        draft = self.output.story_draft
        draft.chapters.append(
            Chapter(
                chapter_number=3, title="C3", content="L1 prose. " * 10, summary="s"
            )
        )
        return draft

    with (
        patch("pipeline.orchestrator_checkpoint.find_checkpoint_path", lambda n: None),
        patch(
            "pipeline.orchestrator.PipelineOrchestrator.continue_story", _fake_continue
        ),
        patch("api.continuation_routes.enhance_tail", lambda *a, **k: 0),
    ):
        resp = _post_continue(client, run_enhancement=True)

    data = [e for e in _sse_events(resp.text) if e.get("type") == "done"][0]["data"]
    assert data["enhanced_chapters"] == 0
    assert [c["number"] for c in data["new_chapters"]] == [3]
    assert data["new_chapters"][0]["content"].startswith("L1 prose.")


# ── Outline preview / approved-outline write ──────────────────────────────


def _outline(number: int, title: str = "Dàn ý", summary: str = "Tóm tắt") -> dict:
    from models.schemas import ChapterOutline

    return ChapterOutline(
        chapter_number=number, title=title, summary=summary
    ).model_dump()


def test_outline_preview_returns_plan_without_writing(client):
    """Preview must plan only — no chapter may be written."""
    captured = {}

    def _fake_outlines(self, **kwargs):
        from models.schemas import ChapterOutline

        captured.update(kwargs)
        return [
            ChapterOutline(chapter_number=3, title="Manh mối", summary="Tới Trấn Nam")
        ]

    with (
        patch("pipeline.orchestrator_checkpoint.find_checkpoint_path", lambda n: None),
        patch(
            "pipeline.orchestrator.PipelineOrchestrator.generate_continuation_outlines",
            _fake_outlines,
        ),
    ):
        resp = client.post(
            "/api/pipeline/continue/library/outlines",
            json={
                "story": _payload().model_dump(),
                "additional_chapters": 1,
                "direction": "Hé lộ bí mật",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["existing_chapters"] == 2
    assert data["hydration_source"] == "payload"
    assert [o["title"] for o in data["outlines"]] == ["Manh mối"]
    # The user's steering must reach the planner.
    assert captured["direction"] == "Hé lộ bí mật"
    assert captured["additional_chapters"] == 1


def test_outline_preview_clamps_to_target(client):
    captured = {}

    def _fake_outlines(self, **kwargs):
        from models.schemas import ChapterOutline

        captured.update(kwargs)
        return [ChapterOutline(chapter_number=3, title="C3", summary="s")]

    with (
        patch("pipeline.orchestrator_checkpoint.find_checkpoint_path", lambda n: None),
        patch(
            "pipeline.orchestrator.PipelineOrchestrator.generate_continuation_outlines",
            _fake_outlines,
        ),
    ):
        resp = client.post(
            "/api/pipeline/continue/library/outlines",
            json={
                "story": _payload(targetChapters=3).model_dump(),
                "additional_chapters": 10,
            },
        )

    assert resp.status_code == 200
    assert captured["additional_chapters"] == 1
    assert resp.json()["note"]


def test_outline_preview_rejects_completed_story(client):
    with patch("pipeline.orchestrator_checkpoint.find_checkpoint_path", lambda n: None):
        resp = client.post(
            "/api/pipeline/continue/library/outlines",
            json={"story": _payload(targetChapters=2).model_dump()},
        )
    assert resp.status_code == 400
    assert "đã đạt" in resp.json()["error"]


def test_outline_preview_rejects_empty_story(client):
    resp = client.post(
        "/api/pipeline/continue/library/outlines",
        json={"story": _payload(chapters=[]).model_dump()},
    )
    assert resp.status_code == 400


def test_continue_library_writes_approved_outlines_verbatim(client):
    """Approved outlines must be written as-is, never re-planned."""
    captured = {}

    def _fake_write(self, **kwargs):
        captured.update(kwargs)
        draft = self.output.story_draft
        draft.chapters.append(
            Chapter(chapter_number=3, title="C3", content="x " * 20, summary="s")
        )
        return draft

    def _boom(self, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("continue_story must not re-plan approved outlines")

    with (
        patch("pipeline.orchestrator_checkpoint.find_checkpoint_path", lambda n: None),
        patch(
            "pipeline.orchestrator.PipelineOrchestrator.write_from_outlines",
            _fake_write,
        ),
        patch("pipeline.orchestrator.PipelineOrchestrator.continue_story", _boom),
    ):
        resp = _post_continue(
            client,
            outlines=[_outline(3, "Máu trên tuyết", "Nhân chứng bị giết")],
        )

    assert resp.status_code == 200
    written = captured["outlines"]
    assert [o.title for o in written] == ["Máu trên tuyết"]
    assert written[0].summary == "Nhân chứng bị giết"


def test_continue_library_rejects_malformed_outlines(client):
    with patch("pipeline.orchestrator_checkpoint.find_checkpoint_path", lambda n: None):
        resp = _post_continue(client, outlines=[{"nope": True}])

    events = _sse_events(resp.text)
    assert any(
        e.get("type") == "error" and "Dàn ý" in str(e.get("data")) for e in events
    )


def test_continue_library_clamps_approved_outlines_to_target(client):
    """More outlines than the arc allows must not overshoot the target."""
    captured = {}

    def _fake_write(self, **kwargs):
        captured.update(kwargs)
        draft = self.output.story_draft
        draft.chapters.append(
            Chapter(chapter_number=3, title="C3", content="x " * 20, summary="s")
        )
        return draft

    with (
        patch("pipeline.orchestrator_checkpoint.find_checkpoint_path", lambda n: None),
        patch(
            "pipeline.orchestrator.PipelineOrchestrator.write_from_outlines",
            _fake_write,
        ),
    ):
        resp = _post_continue(
            client,
            story=_payload(targetChapters=3).model_dump(),
            outlines=[_outline(3), _outline(4), _outline(5)],
        )

    assert resp.status_code == 200
    assert len(captured["outlines"]) == 1
