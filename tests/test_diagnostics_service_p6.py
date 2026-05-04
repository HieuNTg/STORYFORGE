"""Unit tests for build_semantic_diagnostics (Sprint 2 P6).

Covers:
  - Empty story (no Sprint-2 data) → returns None
  - Story with all three signals (outline_metrics + semantic_findings) → full dict
  - Story with only outline_metrics (no chapter findings) → partial dict
  - Story with only chapter findings (no outline_metrics) → partial dict
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool


# ---------------------------------------------------------------------------
# Helpers — build an in-memory SQLite DB with the minimal schema
# ---------------------------------------------------------------------------

_CREATE_STORIES = """
CREATE TABLE IF NOT EXISTS stories (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    genre TEXT NOT NULL DEFAULT '',
    synopsis TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

_CREATE_CHAPTERS = """
CREATE TABLE IF NOT EXISTS chapters (
    id TEXT PRIMARY KEY,
    story_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    word_count INTEGER NOT NULL DEFAULT 0,
    quality_score REAL NOT NULL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    negotiated_contract TEXT,
    contract_reconciliation_warnings TEXT,
    semantic_findings TEXT
)
"""

_CREATE_PIPELINE_RUNS = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id TEXT PRIMARY KEY,
    story_id TEXT,
    genre TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'running',
    layer_reached INTEGER NOT NULL DEFAULT 1,
    token_usage INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    handoff_envelope TEXT,
    handoff_health TEXT,
    handoff_signals_version TEXT,
    outline_metrics TEXT
)
"""


def _engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with eng.connect() as conn:
        conn.execute(text(_CREATE_STORIES))
        conn.execute(text(_CREATE_CHAPTERS))
        conn.execute(text(_CREATE_PIPELINE_RUNS))
        conn.commit()
    return eng


_OUTLINE_METRICS = {
    "schema_version": "1.0.0",
    "conflict_web_density": 0.50,
    "arc_trajectory_variance": 0.40,
    "pacing_distribution_skew": 0.70,
    "beat_coverage_ratio": 0.80,
    "character_screen_time_gini": 0.20,
    "overall_score": 0.72,
    "num_chapters": 5,
    "num_characters": 3,
    "num_conflict_nodes": 3,
    "num_seeds": 4,
    "num_arc_waypoints": 6,
}

_SEMANTIC_FINDINGS_CHAPTER_1 = {
    "schema_version": "1.0.0",
    "chapter_num": 1,
    "embedding_model": "test-model",
    "payoff_matches": [
        {
            "seed_id": "seed001",
            "chapter_num": 1,
            "role": "payoff",
            "matched": True,
            "confidence": 0.75,
            "threshold_used": 0.62,
            "matched_span": "The hero revealed the sword.",
            "method": "embedding",
        },
        {
            "seed_id": "seed002",
            "chapter_num": 1,
            "role": "payoff",
            "matched": False,
            "confidence": 0.30,
            "threshold_used": 0.62,
            "matched_span": None,
            "method": "embedding",
        },
    ],
    "structural_findings": [
        {
            "finding_type": "missing_character",
            "chapter_num": 1,
            "severity": 0.90,
            "description": "Required character 'Lan' not found",
            "fix_hint": "Include Lan",
            "detection_method": "ner",
            "evidence": [],
            "confidence": 1.0,
        },
        {
            "finding_type": "missing_key_event",
            "chapter_num": 1,
            "severity": 0.65,
            "description": "Thread 'betrayal arc' not advanced",
            "fix_hint": "Advance betrayal",
            "detection_method": "embedding",
            "evidence": [],
            "confidence": 0.80,
        },
    ],
}

_CONTRACT_CHAPTER_1 = {
    "pacing_type": "rising",
    "drama_target": 0.7,
    "reconciled": True,
}


def _insert_story(conn, sid: str) -> None:
    conn.execute(
        text("INSERT INTO stories (id, title, genre) VALUES (:id, :title, :genre)"),
        {"id": sid, "title": "Test Story", "genre": "Tiên Hiệp"},
    )


def _insert_run(conn, run_id: str, story_id: str, outline_metrics=None) -> None:
    om_json = json.dumps(outline_metrics) if outline_metrics else None
    conn.execute(
        text(
            "INSERT INTO pipeline_runs (id, story_id, genre, outline_metrics) "
            "VALUES (:id, :sid, :genre, :om)"
        ),
        {"id": run_id, "sid": story_id, "genre": "Tiên Hiệp", "om": om_json},
    )


def _insert_chapter(
    conn,
    ch_id: str,
    story_id: str,
    ch_num: int,
    semantic_findings=None,
    contract=None,
) -> None:
    sf_json = json.dumps(semantic_findings) if semantic_findings else None
    ct_json = json.dumps(contract) if contract else None
    conn.execute(
        text(
            "INSERT INTO chapters "
            "(id, story_id, chapter_number, title, content, semantic_findings, negotiated_contract) "
            "VALUES (:id, :sid, :num, :title, :content, :sf, :ct)"
        ),
        {
            "id": ch_id,
            "sid": story_id,
            "num": ch_num,
            "title": f"Chapter {ch_num}",
            "content": "content here",
            "sf": sf_json,
            "ct": ct_json,
        },
    )


# ---------------------------------------------------------------------------
# Patch diagnostics_service to use in-memory engine
# ---------------------------------------------------------------------------

import importlib
import services.diagnostics_service as _svc_module


@pytest.fixture()
def patched_service(monkeypatch):
    """Patch _sync_engine in diagnostics_service with an in-memory engine fixture."""
    eng = _engine()
    monkeypatch.setattr(_svc_module, "_sync_engine", lambda: eng)
    return eng


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBuildSemanticDiagnostics:
    def test_unknown_story_returns_none(self, patched_service):
        from services.diagnostics_service import build_semantic_diagnostics
        result = build_semantic_diagnostics("nonexistent-id")
        assert result is None

    def test_pre_sprint2_story_returns_none(self, patched_service):
        """Story exists but has no Sprint-2 data → None."""
        eng = patched_service
        sid = str(uuid.uuid4())
        with eng.connect() as conn:
            _insert_story(conn, sid)
            _insert_chapter(conn, str(uuid.uuid4()), sid, 1)
            _insert_run(conn, str(uuid.uuid4()), sid, outline_metrics=None)
            conn.commit()

        from services.diagnostics_service import build_semantic_diagnostics
        result = build_semantic_diagnostics(sid)
        assert result is None

    def test_full_story_returns_complete_dict(self, patched_service):
        """Story with outline_metrics + semantic_findings → full dict."""
        eng = patched_service
        sid = str(uuid.uuid4())
        with eng.connect() as conn:
            _insert_story(conn, sid)
            _insert_chapter(
                conn,
                str(uuid.uuid4()),
                sid,
                1,
                semantic_findings=_SEMANTIC_FINDINGS_CHAPTER_1,
                contract=_CONTRACT_CHAPTER_1,
            )
            _insert_run(
                conn, str(uuid.uuid4()), sid, outline_metrics=_OUTLINE_METRICS
            )
            conn.commit()

        from services.diagnostics_service import build_semantic_diagnostics
        result = build_semantic_diagnostics(sid)

        assert result is not None
        assert result["story_id"] == sid

        # outline_metrics present
        assert result["outline_metrics"] is not None
        assert result["outline_metrics"]["overall_score"] == 0.72

        # per_chapter populated
        assert len(result["per_chapter"]) == 1
        ch = result["per_chapter"][0]
        assert ch["chapter_num"] == 1
        assert ch["semantic_findings"] is not None
        assert ch["contract"] is not None
        assert ch["contract"]["pacing_type"] == "rising"

        # summary
        summary = result["summary"]
        assert summary["total_payoff_matched"] == 1  # seed001 matched
        assert summary["total_payoff_missed"] == 1   # seed002 missed (conf=0.30, floor=0.57)
        assert summary["total_payoff_weak"] == 0
        assert summary["total_structural_findings_by_severity"]["critical"] == 1  # sev=0.90
        assert summary["total_structural_findings_by_severity"]["major"] == 1    # sev=0.65
        assert summary["total_structural_findings_by_severity"]["minor"] == 0

    def test_only_outline_metrics_returns_partial(self, patched_service):
        """Story with only outline_metrics, no chapter findings → partial dict."""
        eng = patched_service
        sid = str(uuid.uuid4())
        with eng.connect() as conn:
            _insert_story(conn, sid)
            _insert_chapter(conn, str(uuid.uuid4()), sid, 1)  # no findings
            _insert_run(
                conn, str(uuid.uuid4()), sid, outline_metrics=_OUTLINE_METRICS
            )
            conn.commit()

        from services.diagnostics_service import build_semantic_diagnostics
        result = build_semantic_diagnostics(sid)

        assert result is not None
        assert result["outline_metrics"] is not None
        assert result["per_chapter"][0]["semantic_findings"] is None
        assert result["summary"]["total_payoff_matched"] == 0

    def test_only_chapter_findings_no_outline_metrics(self, patched_service):
        """Story with chapter findings but no outline_metrics → partial dict."""
        eng = patched_service
        sid = str(uuid.uuid4())
        with eng.connect() as conn:
            _insert_story(conn, sid)
            _insert_chapter(
                conn,
                str(uuid.uuid4()),
                sid,
                1,
                semantic_findings=_SEMANTIC_FINDINGS_CHAPTER_1,
            )
            _insert_run(conn, str(uuid.uuid4()), sid, outline_metrics=None)
            conn.commit()

        from services.diagnostics_service import build_semantic_diagnostics
        result = build_semantic_diagnostics(sid)

        assert result is not None
        assert result["outline_metrics"] is None
        assert result["per_chapter"][0]["semantic_findings"] is not None
        assert result["summary"]["outline_floors_violated"] == []

    def test_floors_violated_detected(self, patched_service):
        """Low outline metrics → floors_violated populated."""
        eng = patched_service
        sid = str(uuid.uuid4())
        low_metrics = dict(_OUTLINE_METRICS)
        low_metrics["conflict_web_density"] = 0.05  # below 0.10 floor
        low_metrics["beat_coverage_ratio"] = 0.40   # below 0.50 floor
        with eng.connect() as conn:
            _insert_story(conn, sid)
            _insert_chapter(
                conn,
                str(uuid.uuid4()),
                sid,
                1,
                semantic_findings=_SEMANTIC_FINDINGS_CHAPTER_1,
            )
            _insert_run(conn, str(uuid.uuid4()), sid, outline_metrics=low_metrics)
            conn.commit()

        from services.diagnostics_service import build_semantic_diagnostics
        result = build_semantic_diagnostics(sid)

        violated = result["summary"]["outline_floors_violated"]
        assert "conflict_web_density" in violated
        assert "beat_coverage_ratio" in violated
        # arc_var=0.40 passes 0.10 floor; pacing_skew=0.70 passes 0.30
        assert "arc_trajectory_variance" not in violated
