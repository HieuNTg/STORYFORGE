"""End-to-end Sprint 1 handoff test (Phase 7).

Exercises the full L1→L2 handoff persistence path against a real (temp)
SQLite database without any LLM calls:

1. Build an L1Handoff envelope from a deterministic mocked draft.
2. Run the handoff gate (strict-mode autouse fixture).
3. Persist envelope + per-chapter NegotiatedChapterContracts via the same
   helpers the orchestrator uses (`_persist_handoff_to_db`,
   `_persist_chapter_contract_to_db`).
4. Assert pipeline_runs row carries the envelope + signal_health.
5. Assert chapters rows carry reconciled negotiated_contract.
6. Hit `GET /api/diagnostics/handoff/{story_id}` via FastAPI TestClient
   and verify the returned payload.

Why not invoke `run_full_pipeline`? It pulls in plugin manager, LLM
client, multi-agent debate, image producer, etc. — each of which would
need separate mocking and would not exercise *more* of the Sprint 1
surface than the helpers do. Per CLAUDE.md "Surgical Changes" guideline
we test the persistence chain that Sprint 1 actually owns.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from api.diagnostics_routes import router as diagnostics_router
from models.db_models import Chapter, PipelineRun, Story
from models.handoff_schemas import L1Handoff, NegotiatedChapterContract
from pipeline.handoff_gate import enforce_handoff, reconcile_contract
from pipeline.layer1_story.handoff_builder import build_l1_handoff
from pipeline.orchestrator_layers import (
    _persist_chapter_contract_to_db,
    _persist_handoff_to_db,
)
from services import diagnostics_service


_FIXTURE = Path(__file__).parent / "fixtures" / "sprint1_e2e_llm_responses.json"
_GOLDEN_PATH = Path(__file__).parent / "golden" / "sprint1_3ch.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_fixture() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


class _Char:
    def __init__(self, name: str, character_id: str):
        self.name = name
        self.character_id = character_id


class _Outline:
    def __init__(self, chapter_number: int):
        self.chapter_number = chapter_number


class _Draft:
    """Light SimpleNamespace-style draft mirroring the attrs the builder reads."""

    def __init__(self, fixture: dict):
        self.characters = [_Char(c["name"], c["character_id"]) for c in fixture["characters"]]
        self.outlines = [_Outline(o["chapter_number"]) for o in fixture["outlines"]]
        self.chapters = []  # populated separately for golden hashing
        self.conflict_web = list(fixture["conflict_web"])
        self.foreshadowing_plan = list(fixture["foreshadowing_plan"])
        self.arc_waypoints = list(fixture["arc_waypoints"])
        self.open_threads = list(fixture["open_threads"])
        self.voice_fingerprints = list(fixture["voice_fingerprints"])
        self.voice_profiles = []


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Spin up an isolated SQLite DB with the full schema applied."""
    db_path = tmp_path / "sprint1_e2e.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    # diagnostics_service caches _DB_URL at import time → patch the module global
    monkeypatch.setattr(diagnostics_service, "_DB_URL", db_url)

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    # Only the three tables Sprint 1 touches — full Base.metadata.create_all
    # blows up on SQLite because audit_logs uses JSONB.
    for table in (Story.__table__, Chapter.__table__, PipelineRun.__table__):
        table.create(engine, checkfirst=True)
    return engine, db_url


@pytest.fixture
def fixture_data():
    return _load_fixture()


@pytest.fixture
def diagnostics_client():
    """Mount only the diagnostics router on a minimal FastAPI app."""
    app = FastAPI()
    app.include_router(diagnostics_router, prefix="/api")
    return TestClient(app)


def _seed_story_and_run(engine, story_id: str) -> str:
    """Insert minimal stories + pipeline_runs rows so persistence helpers can update."""
    from sqlalchemy.orm import Session
    with Session(engine) as session:
        story = Story(
            id=story_id,
            title="Lý Huyền Truyền Kỳ",
            genre="tien_hiep",
            synopsis="Câu chuyện tu tiên",
            status="completed",
        )
        session.add(story)
        run_id = "ffffffff-eeee-dddd-cccc-" + story_id.replace("-", "")[-12:]
        run = PipelineRun(
            id=run_id,
            story_id=story_id,
            genre="tien_hiep",
            status="completed",
            layer_reached=2,
            token_usage=0,
        )
        session.add(run)
        session.commit()
    return run_id


def _insert_chapters(engine, story_id: str, fixture: dict) -> None:
    """Insert chapters so chapter-contract persistence has rows to update."""
    from sqlalchemy.orm import Session
    with Session(engine) as session:
        for outline in fixture["outlines"]:
            ch_num = outline["chapter_number"]
            content = fixture["chapter_contents"][str(ch_num)]
            session.add(Chapter(
                id=f"ddddddee-aaaa-bbbb-cccc-aaaaaaaa{ch_num:04d}",
                story_id=story_id,
                chapter_number=ch_num,
                title=outline["title"],
                content=content,
                word_count=len(content.split()),
            ))
        session.commit()


# ---------------------------------------------------------------------------
# E2E test
# ---------------------------------------------------------------------------


def test_handoff_e2e_3_chapter_run(temp_db, fixture_data, diagnostics_client):
    """Full Sprint 1 path: build → enforce → persist → diagnose.

    Uses `_persist_handoff_to_db` / `_persist_chapter_contract_to_db` directly
    (ORM-based after Bug A fix) and verifies the diagnostics endpoint returns
    correct signal health (Bug B fix: JSON string columns are now decoded).
    """
    engine, _db_url = temp_db
    story_id = fixture_data["story_id"]
    sid_stripped = story_id.replace("-", "")

    # Seed story + run + chapters
    _seed_story_and_run(engine, story_id)
    _insert_chapters(engine, story_id, fixture_data)

    # 1. Build envelope
    draft = _Draft(fixture_data)
    envelope = build_l1_handoff(draft, story_id=story_id)
    assert isinstance(envelope, L1Handoff)

    # 2. Gate (strict-mode) — clean envelope passes
    out = enforce_handoff(envelope)
    assert out is envelope

    # All 5 signals "ok"
    for sig, h in envelope.signal_health.items():
        assert h.status == "ok", f"{sig} status={h.status}"

    # 3. Reconcile contracts
    contracts = []
    for raw in fixture_data["negotiated_contracts"]:
        nc = NegotiatedChapterContract(**raw)
        reconciled = reconcile_contract(nc)
        contracts.append(reconciled)

    # 4. Persist via production helpers (Bug A fix: ORM, not raw SQL)
    health_dict = {sig: h.model_dump() for sig, h in envelope.signal_health.items()}
    _persist_handoff_to_db(
        story_id=story_id,
        envelope_dict=envelope.model_dump(),
        health_dict=health_dict,
        signals_version=envelope.signals_version,
    )
    for c in contracts:
        _persist_chapter_contract_to_db(
            story_id=story_id,
            chapter_number=c.chapter_num,
            contract_dict=c.model_dump(),
            warnings=list(c.reconciliation_warnings),
        )

    # 5a. Verify pipeline_runs row has envelope + signal_health.
    from sqlalchemy import text
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT handoff_envelope, handoff_health, handoff_signals_version "
                "FROM pipeline_runs WHERE story_id = :sid"
            ),
            {"sid": sid_stripped},
        ).fetchone()
    assert row is not None
    persisted_env = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    persisted_health = json.loads(row[1]) if isinstance(row[1], str) else row[1]
    assert persisted_env["story_id"] == story_id
    assert persisted_env["signals_version"] == "1.0.0"
    assert all(persisted_health[s]["status"] == "ok" for s in persisted_health)
    assert row[2] == "1.0.0"

    # 5b. Verify each chapter has a reconciled contract
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT chapter_number, negotiated_contract, contract_reconciliation_warnings "
                "FROM chapters WHERE story_id = :sid ORDER BY chapter_number"
            ),
            {"sid": sid_stripped},
        ).fetchall()
    assert len(rows) == 3
    for ch_num, contract_json, _warnings in rows:
        contract = json.loads(contract_json) if isinstance(contract_json, str) else contract_json
        assert contract["chapter_num"] == ch_num
        assert contract["reconciled"] is True

    # 5c. Diagnostics endpoint returns expected payload.
    # Query with dashed form — diagnostics_service uses raw-SQL SELECT with
    # story_id, and SQLite stores it stripped; the service's stories query
    # also uses raw SQL so we pass stripped form to match.
    resp = diagnostics_client.get(f"/api/diagnostics/handoff/{sid_stripped}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["story_id"] == sid_stripped

    # Bug B fixed: JSON string columns are now decoded → signal_health populated
    assert body["signals_ok"] == 5, (
        "All 5 signals should be ok after Bug B fix (json.loads shim in diagnostics_service)"
    )
    assert body["signals_total"] == 5
    assert len(body["per_chapter_contracts"]) == 3


def test_persist_helpers_bug_documentation(temp_db, fixture_data):
    """FIXED — ORM-based persist now correctly writes on SQLite.

    Previously `_persist_handoff_to_db` used raw SQL which bypassed
    SQLAlchemy's UUID coercion, causing the UPDATE to match 0 rows on SQLite.
    The fix switches to ORM queries so type coercion runs correctly.

    This test now asserts the CORRECT behaviour (envelope is written).
    """
    engine, _ = temp_db
    story_id = fixture_data["story_id"]
    _seed_story_and_run(engine, story_id)

    from pipeline.orchestrator_layers import _persist_handoff_to_db
    draft = _Draft(fixture_data)
    envelope = build_l1_handoff(draft, story_id=story_id)
    health_dict = {sig: h.model_dump() for sig, h in envelope.signal_health.items()}
    _persist_handoff_to_db(
        story_id=story_id,
        envelope_dict=envelope.model_dump(),
        health_dict=health_dict,
        signals_version=envelope.signals_version,
    )

    # Fixed: ORM update goes through type coercion, so the envelope is written.
    from sqlalchemy import text
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT story_id, handoff_envelope FROM pipeline_runs")
        ).fetchall()
    assert len(rows) == 1
    stored_sid, stored_env = rows[0]
    assert stored_sid == story_id.replace("-", ""), "ORM strips dashes on SQLite"
    assert stored_env is not None, (
        "ORM persist must write handoff_envelope (Bug A fix regression)"
    )
    persisted = json.loads(stored_env) if isinstance(stored_env, str) else stored_env
    assert persisted["story_id"] == story_id
    assert persisted["signals_version"] == "1.0.0"


def test_diagnostics_returns_404_for_missing_story(temp_db, diagnostics_client):
    resp = diagnostics_client.get("/api/diagnostics/handoff/no_such_story")
    assert resp.status_code == 404


def test_diagnostics_returns_404_for_premigration_run(temp_db, diagnostics_client):
    """Story exists, run exists, but handoff_envelope is NULL → 404."""
    engine, _ = temp_db
    pre_id = "abcdef01-2345-6789-abcd-ef0123456789"
    _seed_story_and_run(engine, pre_id)
    resp = diagnostics_client.get(f"/api/diagnostics/handoff/{pre_id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Golden snapshot — chapter content hashes only (per Risk #1, no envelope JSON)
# ---------------------------------------------------------------------------


def _hash_chapter(content: str) -> str:
    import hashlib
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def test_golden_chapter_content_hashes_unchanged(fixture_data):
    """Re-running with the same mocked LLM responses must produce identical
    chapter content hashes byte-for-byte. Failure indicates the test fixture
    drifted, NOT the envelope wiring (envelope is new per Risk #1)."""
    actual = {
        ch_num: _hash_chapter(content)
        for ch_num, content in fixture_data["chapter_contents"].items()
    }

    if not _GOLDEN_PATH.exists():
        # First-run bootstrap — write and assert the count is right
        _GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        _GOLDEN_PATH.write_text(
            json.dumps(
                {
                    "_comment": (
                        "Sprint 1 golden snapshot: SHA-256 of each mocked chapter "
                        "content. If a hash mismatch fails this test, the chapter "
                        "prose changed unexpectedly — investigate L1 generation, "
                        "not envelope wiring (envelope is plumbing-only per Risk #1)."
                    ),
                    "chapter_hashes": actual,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    expected = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))["chapter_hashes"]
    assert actual == expected, (
        "chapter prose changed unexpectedly — investigate L1 generation, "
        "not envelope wiring. If the fixture was edited intentionally, "
        f"delete {_GOLDEN_PATH} and re-run."
    )
    assert len(actual) == 3
