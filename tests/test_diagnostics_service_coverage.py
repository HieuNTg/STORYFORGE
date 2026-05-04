"""Coverage tests for `services.diagnostics_service.build_handoff_diagnostics`.

The dict-branches in the service can't be reached on SQLite end-to-end (JSON
columns round-trip as strings on raw SQL read — see e2e test docstring). To
cover those branches we stub `_sync_engine` with a fake engine that returns
already-decoded dicts, mirroring native PostgreSQL JSONB behaviour.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from models.db_models import Chapter, PipelineRun, Story
from services import diagnostics_service


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "diagsvc.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setattr(diagnostics_service, "_DB_URL", db_url)
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    for table in (Story.__table__, Chapter.__table__, PipelineRun.__table__):
        table.create(engine, checkfirst=True)
    return engine


def _seed_story_only(engine, sid: str, with_run=False, env=None, health=None):
    """Insert a story (and optionally a run) via ORM."""
    with Session(engine) as s:
        s.add(Story(id=sid, title="T", genre="g", synopsis="syn", status="ok"))
        if with_run:
            s.add(PipelineRun(
                id="ffffffff-eeee-dddd-cccc-bbbbbbbbbbbb",
                story_id=sid,
                genre="g", status="ok", layer_reached=2, token_usage=0,
                handoff_envelope=env,
                handoff_health=health,
                handoff_signals_version="1.0.0" if env else None,
            ))
        s.commit()


def test_returns_none_when_story_missing(temp_db):
    assert diagnostics_service.build_handoff_diagnostics("no-such-story") is None


def test_returns_none_for_premigration_run(monkeypatch):
    """Story exists, run exists, but handoff_envelope NULL → returns None.

    Uses stubbed engine because SQLite raw-SQL UUID matching is broken
    (see e2e test docstring). On native PostgreSQL the column type would
    accept dashed UUIDs natively.
    """
    eng = _build_fake_engine(
        story_row=_FakeRow(("x",)),
        run_row=None,  # no row with handoff_envelope IS NOT NULL
        chapter_rows=[],
    )
    monkeypatch.setattr(diagnostics_service, "_sync_engine", lambda: eng)
    assert diagnostics_service.build_handoff_diagnostics("x") is None


# ---------------------------------------------------------------------------
# Stubbed-engine tests for the dict branches (PG-JSONB simulation)
# ---------------------------------------------------------------------------


class _FakeRow(tuple):
    """Just a tuple, but explicit for clarity."""


def _build_fake_engine(story_row, run_row, chapter_rows):
    """Build a MagicMock engine that returns the given rows in order."""
    eng = MagicMock()

    @contextmanager
    def _connect():
        conn = MagicMock()
        # Each `conn.execute(...)` returns a result whose `.fetchone()` /
        # `.fetchall()` is queued in call order.
        results = [
            MagicMock(fetchone=MagicMock(return_value=story_row)),
            MagicMock(fetchone=MagicMock(return_value=run_row)),
            MagicMock(fetchall=MagicMock(return_value=chapter_rows)),
        ]
        conn.execute = MagicMock(side_effect=results)
        yield conn

    eng.connect = _connect
    eng.dispose = MagicMock()
    return eng


def test_envelope_dict_branch_aggregates_signal_health(monkeypatch):
    """Covers lines 83-93: envelope.signal_health is dict, items are dicts."""
    env = {
        "story_id": "x",
        "signals_version": "1.0.0",
        "signal_health": {
            "conflict_web": {"status": "ok", "item_count": 3, "reason": None},
            "foreshadowing": {"status": "ok", "item_count": 1, "reason": None},
            "arcs": {"status": "empty", "item_count": 0, "reason": "no waypoints"},
            "threads": {"status": "ok", "item_count": 2, "reason": None},
            "voice": {"status": "malformed", "item_count": 0, "reason": "bad payload"},
            "garbage": "not-a-dict",  # branch: non-dict skipped
        },
    }
    eng = _build_fake_engine(
        story_row=_FakeRow(("x",)),
        run_row=_FakeRow((env, {}, "1.0.0")),
        chapter_rows=[],
    )
    monkeypatch.setattr(diagnostics_service, "_sync_engine", lambda: eng)
    out = diagnostics_service.build_handoff_diagnostics("x")
    assert out is not None
    assert out["signals_total"] == 5
    assert out["signals_ok"] == 3
    assert out["signal_health_summary"]["arcs"]["status"] == "empty"
    assert out["signal_health_summary"]["voice"]["status"] == "malformed"


def test_health_fallback_when_envelope_lacks_signal_health(monkeypatch):
    """Covers lines 94-105: envelope has no signal_health → use health_raw dict."""
    env = {"story_id": "x", "signals_version": "1.0.0"}  # no signal_health
    health = {
        "conflict_web": {"status": "ok", "item_count": 1, "reason": None},
        "foreshadowing": {"status": "ok", "item_count": 1, "reason": None},
        "garbage": 123,  # non-dict skip branch
    }
    eng = _build_fake_engine(
        story_row=_FakeRow(("x",)),
        run_row=_FakeRow((env, health, "1.0.0")),
        chapter_rows=[],
    )
    monkeypatch.setattr(diagnostics_service, "_sync_engine", lambda: eng)
    out = diagnostics_service.build_handoff_diagnostics("x")
    assert out is not None
    assert out["signals_ok"] == 2
    assert out["signals_total"] == 2


def test_per_chapter_skips_non_dict_contract(monkeypatch):
    """Covers line 124-125: contract is not a dict → continue."""
    env = {"story_id": "x", "signals_version": "1.0.0", "signal_health": {}}
    chapter_rows = [
        _FakeRow((1, {"chapter_num": 1, "pacing_type": "setup", "drama_target": 0.3, "reconciled": True}, [])),
        _FakeRow((2, None, None)),  # non-dict contract → skipped
        _FakeRow((3, {"chapter_num": 3, "pacing_type": "climax", "drama_target": 0.78, "reconciled": True}, ["w"])),
    ]
    eng = _build_fake_engine(
        story_row=_FakeRow(("x",)),
        run_row=_FakeRow((env, {}, "1.0.0")),
        chapter_rows=chapter_rows,
    )
    monkeypatch.setattr(diagnostics_service, "_sync_engine", lambda: eng)
    out = diagnostics_service.build_handoff_diagnostics("x")
    assert out is not None
    nums = [c["chapter_number"] for c in out["per_chapter_contracts"]]
    assert nums == [1, 3]
    # Warnings preserved when present
    ch3 = next(c for c in out["per_chapter_contracts"] if c["chapter_number"] == 3)
    assert ch3["reconciliation_warnings"] == ["w"]


def test_per_chapter_warnings_fallback_to_contract_field(monkeypatch):
    """When the warnings column is not a list, falls back to contract dict's field."""
    env = {"story_id": "x", "signals_version": "1.0.0", "signal_health": {}}
    chapter_rows = [
        _FakeRow((1, {
            "chapter_num": 1, "pacing_type": "setup",
            "drama_target": 0.3, "reconciled": True,
            "reconciliation_warnings": ["from-contract"],
        }, "not-a-list")),
    ]
    eng = _build_fake_engine(
        story_row=_FakeRow(("x",)),
        run_row=_FakeRow((env, {}, "1.0.0")),
        chapter_rows=chapter_rows,
    )
    monkeypatch.setattr(diagnostics_service, "_sync_engine", lambda: eng)
    out = diagnostics_service.build_handoff_diagnostics("x")
    assert out["per_chapter_contracts"][0]["reconciliation_warnings"] == ["from-contract"]


def test_exception_path_returns_none(monkeypatch):
    """Covers exception handler 144-146 — engine connect() raises mid-query."""
    eng = MagicMock()
    eng.connect = MagicMock(side_effect=RuntimeError("kaboom"))
    eng.dispose = MagicMock()
    monkeypatch.setattr(diagnostics_service, "_sync_engine", lambda: eng)
    assert diagnostics_service.build_handoff_diagnostics("anything") is None
    eng.dispose.assert_called_once()  # finally block ran
