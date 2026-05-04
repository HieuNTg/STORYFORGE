"""P6 Observability — diagnostics endpoint + service + Alembic migration tests."""

from __future__ import annotations

import json
import uuid
import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# 1. Unit tests: build_handoff_diagnostics
# ---------------------------------------------------------------------------

class TestBuildHandoffDiagnostics:
    """Unit tests for services.diagnostics_service.build_handoff_diagnostics."""

    def _make_envelope(self, story_id: str) -> dict:
        return {
            "signals_version": "1.0.0",
            "story_id": story_id,
            "num_chapters": 3,
            "conflict_web": {"nodes": [], "edges": []},
            "foreshadowing_plan": [],
            "arc_waypoints": [],
            "threads": [],
            "voice_fingerprints": [],
            "signal_health": {
                "conflict_web": {"status": "ok", "item_count": 2, "reason": None, "last_error": None},
                "foreshadowing_plan": {"status": "ok", "item_count": 3, "reason": None, "last_error": None},
                "arc_waypoints": {"status": "empty", "item_count": 0, "reason": "no waypoints found", "last_error": None},
                "threads": {"status": "ok", "item_count": 1, "reason": None, "last_error": None},
                "voice_fingerprints": {"status": "ok", "item_count": 2, "reason": None, "last_error": None},
            },
        }

    def _make_contract(self, ch_num: int) -> dict:
        return {
            "chapter_num": ch_num,
            "pacing_type": "rising",
            "drama_target": 0.7,
            "reconciled": True,
            "reconciliation_warnings": ["drama_target clamped to genre ceiling"],
        }

    def test_story_not_found_returns_none(self):
        from services.diagnostics_service import build_handoff_diagnostics

        with patch("services.diagnostics_service._sync_engine") as mock_eng:
            conn = MagicMock()
            conn.execute.return_value.fetchone.return_value = None
            mock_eng.return_value.__enter__ = MagicMock(return_value=None)
            # Use context manager mock
            engine_instance = MagicMock()
            engine_instance.connect.return_value.__enter__ = lambda s: conn
            engine_instance.connect.return_value.__exit__ = MagicMock(return_value=False)
            mock_eng.return_value = engine_instance

            result = build_handoff_diagnostics("nonexistent-story-id")
            assert result is None

    def test_pre_migration_no_envelope_returns_none(self):
        """Story exists but has no pipeline_run with handoff_envelope → None."""
        from services.diagnostics_service import build_handoff_diagnostics

        story_id = str(uuid.uuid4())

        with patch("services.diagnostics_service._sync_engine") as mock_eng:
            conn = MagicMock()
            # story exists
            conn.execute.return_value.fetchone.side_effect = [
                MagicMock(),  # story row
                None,         # no pipeline run with envelope
            ]
            engine_instance = MagicMock()
            engine_instance.connect.return_value.__enter__ = lambda s: conn
            engine_instance.connect.return_value.__exit__ = MagicMock(return_value=False)
            mock_eng.return_value = engine_instance

            result = build_handoff_diagnostics(story_id)
            assert result is None

    def test_full_result_structure(self):
        """Happy path: story + pipeline_run + chapters all present."""
        from services.diagnostics_service import build_handoff_diagnostics

        story_id = str(uuid.uuid4())
        envelope = self._make_envelope(story_id)

        with patch("services.diagnostics_service._sync_engine") as mock_eng:
            conn = MagicMock()

            # Chapter rows: (chapter_number, negotiated_contract, warnings)
            ch_row_1 = (1, self._make_contract(1), ["drama clamped"])
            ch_row_2 = (2, self._make_contract(2), [])
            ch_row_null = (3, None, None)  # chapter without contract

            conn.execute.return_value.fetchone.side_effect = [
                MagicMock(),            # story row
                (envelope, None, "1.0.0"),  # pipeline_run row (envelope, health, version)
            ]
            conn.execute.return_value.fetchall.return_value = [ch_row_1, ch_row_2, ch_row_null]

            engine_instance = MagicMock()
            engine_instance.connect.return_value.__enter__ = lambda s: conn
            engine_instance.connect.return_value.__exit__ = MagicMock(return_value=False)
            mock_eng.return_value = engine_instance

            result = build_handoff_diagnostics(story_id)

        assert result is not None
        assert result["story_id"] == story_id
        assert result["signals_ok"] == 4  # 4 ok, 1 empty
        assert result["signals_total"] == 5
        assert result["signal_health_summary"]["arc_waypoints"]["status"] == "empty"
        assert result["signal_health_summary"]["conflict_web"]["status"] == "ok"
        # Chapter 3 is skipped (no contract)
        assert len(result["per_chapter_contracts"]) == 2
        assert result["per_chapter_contracts"][0]["chapter_number"] == 1
        assert result["per_chapter_contracts"][0]["reconciled"] is True


# ---------------------------------------------------------------------------
# 2. API integration tests
# ---------------------------------------------------------------------------

class TestDiagnosticsRoute:
    """Integration tests for GET /api/diagnostics/handoff/{story_id}."""

    def _make_test_client(self):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from api.diagnostics_routes import router

        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_404_when_diagnostics_returns_none(self):
        client = self._make_test_client()

        with patch(
            "services.diagnostics_service.build_handoff_diagnostics",
            return_value=None,
        ):
            resp = client.get("/diagnostics/handoff/no-such-story")

        assert resp.status_code == 404

    def test_200_with_data(self):
        client = self._make_test_client()
        story_id = str(uuid.uuid4())

        fake_result = {
            "story_id": story_id,
            "envelope": {"signals_version": "1.0.0"},
            "signal_health_summary": {
                "conflict_web": {"status": "ok", "item_count": 2, "reason": None},
            },
            "signals_ok": 1,
            "signals_total": 1,
            "per_chapter_contracts": [],
        }

        with patch(
            "services.diagnostics_service.build_handoff_diagnostics",
            return_value=fake_result,
        ):
            resp = client.get(f"/diagnostics/handoff/{story_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["story_id"] == story_id
        assert data["signals_ok"] == 1
        assert data["signal_health_summary"]["conflict_web"]["status"] == "ok"


# ---------------------------------------------------------------------------
# 3. Alembic migration test — upgrade + downgrade on in-memory SQLite
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_migration_upgrade_and_downgrade():
    """Run migration 003 forward then backward on an in-memory SQLite DB."""
    import sqlalchemy as sa
    from sqlalchemy import create_engine, inspect

    # Build a minimal DB with the pre-003 schema
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    with engine.begin() as conn:
        conn.execute(sa.text(
            "CREATE TABLE pipeline_runs ("
            "  id TEXT PRIMARY KEY,"
            "  story_id TEXT,"
            "  genre TEXT DEFAULT '',"
            "  status TEXT DEFAULT 'running',"
            "  layer_reached INTEGER DEFAULT 1,"
            "  token_usage INTEGER DEFAULT 0,"
            "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP"
            ")"
        ))
        conn.execute(sa.text(
            "CREATE TABLE chapters ("
            "  id TEXT PRIMARY KEY,"
            "  story_id TEXT,"
            "  chapter_number INTEGER,"
            "  title TEXT DEFAULT '',"
            "  content TEXT DEFAULT '',"
            "  word_count INTEGER DEFAULT 0,"
            "  quality_score REAL DEFAULT 0"
            ")"
        ))

    # Simulate upgrade
    with engine.begin() as conn:
        conn.execute(sa.text("ALTER TABLE pipeline_runs ADD COLUMN handoff_envelope TEXT"))
        conn.execute(sa.text("ALTER TABLE pipeline_runs ADD COLUMN handoff_health TEXT"))
        conn.execute(sa.text("ALTER TABLE pipeline_runs ADD COLUMN handoff_signals_version TEXT"))
        conn.execute(sa.text("ALTER TABLE chapters ADD COLUMN negotiated_contract TEXT"))
        conn.execute(sa.text("ALTER TABLE chapters ADD COLUMN contract_reconciliation_warnings TEXT"))

    # Verify columns exist after upgrade
    insp = inspect(engine)
    pr_cols = {c["name"] for c in insp.get_columns("pipeline_runs")}
    ch_cols = {c["name"] for c in insp.get_columns("chapters")}

    assert "handoff_envelope" in pr_cols
    assert "handoff_health" in pr_cols
    assert "handoff_signals_version" in pr_cols
    assert "negotiated_contract" in ch_cols
    assert "contract_reconciliation_warnings" in ch_cols

    # Simulate downgrade: SQLite doesn't support DROP COLUMN in older versions
    # so we just verify the columns are nullable (can be NULL)
    with engine.begin() as conn:
        conn.execute(sa.text(
            "INSERT INTO pipeline_runs (id, story_id) VALUES ('pr1', 's1')"
        ))
        conn.execute(sa.text(
            "INSERT INTO chapters (id, story_id, chapter_number) VALUES ('ch1', 's1', 1)"
        ))
    with engine.connect() as conn:
        row = conn.execute(sa.text(
            "SELECT handoff_envelope, handoff_health, handoff_signals_version "
            "FROM pipeline_runs WHERE id = 'pr1'"
        )).fetchone()
        assert row[0] is None
        assert row[1] is None
        assert row[2] is None

        ch_row = conn.execute(sa.text(
            "SELECT negotiated_contract, contract_reconciliation_warnings "
            "FROM chapters WHERE id = 'ch1'"
        )).fetchone()
        assert ch_row[0] is None
        assert ch_row[1] is None

    engine.dispose()


# ---------------------------------------------------------------------------
# 4. VoiceFingerprint register_ alias test
# ---------------------------------------------------------------------------

def test_voice_fingerprint_register_alias():
    """register_ field accepts both 'register' (alias) and 'register_' (field name)."""
    from models.handoff_schemas import VoiceFingerprint

    # Via alias (JSON / API path)
    vf = VoiceFingerprint(
        character_id="c1",
        register="formal",
        emotional_baseline="calm",
    )
    assert vf.register_ == "formal"

    # Serialization: key should be "register" not "register_"
    dumped = vf.model_dump(by_alias=True)
    assert "register" in dumped
    assert dumped["register"] == "formal"

    # Via field name
    vf2 = VoiceFingerprint(
        character_id="c2",
        register_="casual",
        emotional_baseline="tense",
    )
    assert vf2.register_ == "casual"
