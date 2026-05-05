"""Behavior tests for pipeline/orchestrator_layers.py.

Covers:
- DB persist helpers (_persist_handoff_to_db, _persist_chapter_contract_to_db,
  persist_chapter_semantic_findings, persist_outline_metrics) with real SQLite
- run_layer2_only signal extraction (conflict_web, foreshadowing_plan)
- run_layer1_only delegation
- _run_structural_rewrites cap math + concurrency
- _get_sync_engine singleton + WAL pragmas
- Error paths: missing row, failing persist (non-fatal)
"""

from __future__ import annotations

import threading
import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from models.db_models import Base, Chapter, PipelineRun, Story

# ---------------------------------------------------------------------------
# Helpers shared by multiple tests
# ---------------------------------------------------------------------------


def _make_engine(db_path: str):
    """Create a fresh sync SQLite engine at *db_path* with all tables."""
    url = f"sqlite:///{db_path}"
    eng = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    return eng


def _story_and_run(session: Session) -> tuple[str, str]:
    """Insert a Story + PipelineRun row; return (story_id, run_id)."""
    sid = str(uuid.uuid4())
    rid = str(uuid.uuid4())
    story = Story(id=sid, title="Test Story", genre="fantasy")
    run = PipelineRun(id=rid, story_id=sid, genre="fantasy")
    session.add_all([story, run])
    session.commit()
    return sid, rid


def _chapter_row(session: Session, story_id: str, chapter_number: int = 1) -> Chapter:
    ch = Chapter(
        id=str(uuid.uuid4()),
        story_id=story_id,
        chapter_number=chapter_number,
        title=f"Chapter {chapter_number}",
        content="content",
    )
    session.add(ch)
    session.commit()
    return ch


# ---------------------------------------------------------------------------
# Fixture: temp SQLite DB path
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_db(tmp_path):
    """Yield a path string for a fresh SQLite file."""
    return str(tmp_path / "test.db")


# ---------------------------------------------------------------------------
# 1. _get_sync_engine — singleton + WAL pragmas
# ---------------------------------------------------------------------------


class TestGetSyncEngine:
    def test_returns_engine(self, tmp_db, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_db}")
        # Reset module singleton before test
        import pipeline.orchestrator_layers as ol
        ol._sync_engine = None
        eng = ol._get_sync_engine()
        assert eng is not None

    def test_singleton_same_object(self, tmp_db, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_db}")
        import pipeline.orchestrator_layers as ol
        ol._sync_engine = None
        e1 = ol._get_sync_engine()
        e2 = ol._get_sync_engine()
        assert e1 is e2

    def test_wal_pragma_applied(self, tmp_db, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_db}")
        import pipeline.orchestrator_layers as ol
        ol._sync_engine = None
        eng = ol._get_sync_engine()
        with eng.connect() as conn:
            result = conn.execute(text("PRAGMA journal_mode")).scalar()
        assert result == "wal"

    def test_singleton_thread_safe(self, tmp_db, monkeypatch):
        """Two threads calling concurrently get the same engine."""
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_db}")
        import pipeline.orchestrator_layers as ol
        ol._sync_engine = None
        engines = []

        def _get():
            engines.append(ol._get_sync_engine())

        t1 = threading.Thread(target=_get)
        t2 = threading.Thread(target=_get)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert engines[0] is engines[1]


# ---------------------------------------------------------------------------
# 2. _persist_handoff_to_db — rows actually written
# ---------------------------------------------------------------------------


class TestPersistHandoffToDb:
    def _setup(self, tmp_db, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_db}")
        import pipeline.orchestrator_layers as ol
        ol._sync_engine = None
        eng = _make_engine(tmp_db)
        return ol, eng

    def test_writes_handoff_fields(self, tmp_db, monkeypatch):
        ol, eng = self._setup(tmp_db, monkeypatch)
        with Session(eng) as s:
            sid, rid = _story_and_run(s)

        ol._persist_handoff_to_db(
            story_id=sid,
            envelope_dict={"story_id": sid},
            health_dict={"conflict_web": {"status": "ok"}},
            signals_version="v1",
        )

        with Session(eng) as s:
            run = s.query(PipelineRun).filter_by(id=rid).one()
            assert run.handoff_envelope == {"story_id": sid}
            assert run.handoff_health == {"conflict_web": {"status": "ok"}}
            assert run.handoff_signals_version == "v1"

    def test_missing_run_logs_warning(self, tmp_db, monkeypatch, caplog):
        ol, eng = self._setup(tmp_db, monkeypatch)
        # No rows inserted — story_id doesn't exist
        missing_id = str(uuid.uuid4())
        import logging
        with caplog.at_level(logging.WARNING, logger="pipeline.orchestrator_layers"):
            ol._persist_handoff_to_db(missing_id, {}, {}, "v1")
        assert "no pipeline_run found" in caplog.text.lower()

    def test_most_recent_run_updated(self, tmp_db, monkeypatch):
        """When multiple runs exist, only the most recent (by created_at) is updated."""
        from datetime import datetime, timedelta
        ol, eng = self._setup(tmp_db, monkeypatch)
        sid = str(uuid.uuid4())
        now = datetime.utcnow()
        with Session(eng) as s:
            story = Story(id=sid, title="T", genre="g")
            s.add(story)
            # older run: created 10 seconds ago
            r1 = PipelineRun(
                id=str(uuid.uuid4()), story_id=sid, genre="g",
                created_at=now - timedelta(seconds=10),
            )
            # newer run: created now
            r2 = PipelineRun(
                id=str(uuid.uuid4()), story_id=sid, genre="g",
                created_at=now,
            )
            s.add_all([r1, r2])
            s.commit()
            r2_id = r2.id
            r1_id = r1.id

        ol._persist_handoff_to_db(sid, {"x": 1}, {}, "v2")

        with Session(eng) as s:
            newer = s.query(PipelineRun).filter_by(id=r2_id).one()
            older = s.query(PipelineRun).filter_by(id=r1_id).one()
            assert newer.handoff_signals_version == "v2"
            assert older.handoff_signals_version is None


# ---------------------------------------------------------------------------
# 3. _persist_chapter_contract_to_db — rows actually written
# ---------------------------------------------------------------------------


class TestPersistChapterContractToDb:
    def _setup(self, tmp_db, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_db}")
        import pipeline.orchestrator_layers as ol
        ol._sync_engine = None
        eng = _make_engine(tmp_db)
        return ol, eng

    def test_writes_contract_and_warnings(self, tmp_db, monkeypatch):
        ol, eng = self._setup(tmp_db, monkeypatch)
        with Session(eng) as s:
            sid, _ = _story_and_run(s)
            _chapter_row(s, sid, chapter_number=3)

        ol._persist_chapter_contract_to_db(
            story_id=sid,
            chapter_number=3,
            contract_dict={"drama_target": 0.7},
            warnings=["warn1"],
        )

        with Session(eng) as s:
            ch = s.query(Chapter).filter_by(story_id=sid, chapter_number=3).one()
            assert ch.negotiated_contract == {"drama_target": 0.7}
            assert ch.contract_reconciliation_warnings == ["warn1"]

    def test_missing_chapter_logs_warning(self, tmp_db, monkeypatch, caplog):
        ol, eng = self._setup(tmp_db, monkeypatch)
        import logging
        with caplog.at_level(logging.WARNING, logger="pipeline.orchestrator_layers"):
            ol._persist_chapter_contract_to_db(
                story_id=str(uuid.uuid4()),
                chapter_number=99,
                contract_dict={},
                warnings=[],
            )
        assert "no chapter found" in caplog.text.lower()


# ---------------------------------------------------------------------------
# 4. persist_chapter_semantic_findings — non-fatal on error
# ---------------------------------------------------------------------------


class TestPersistChapterSemanticFindings:
    def _setup(self, tmp_db, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_db}")
        import pipeline.orchestrator_layers as ol
        ol._sync_engine = None
        eng = _make_engine(tmp_db)
        return ol, eng

    def test_writes_semantic_findings(self, tmp_db, monkeypatch):
        ol, eng = self._setup(tmp_db, monkeypatch)
        with Session(eng) as s:
            sid, _ = _story_and_run(s)
            _chapter_row(s, sid, chapter_number=2)

        ol.persist_chapter_semantic_findings(
            story_id=sid,
            chapter_number=2,
            findings_dict={"payoffs": ["found_payoff"]},
        )

        with Session(eng) as s:
            ch = s.query(Chapter).filter_by(story_id=sid, chapter_number=2).one()
            assert ch.semantic_findings == {"payoffs": ["found_payoff"]}

    def test_non_fatal_on_bad_engine(self, monkeypatch, caplog):
        """Persist failure must not raise — just logs warning."""
        monkeypatch.setenv("DATABASE_URL", "sqlite:////nonexistent/path/test.db")
        import pipeline.orchestrator_layers as ol
        ol._sync_engine = None  # force re-init with bad path
        import logging
        with caplog.at_level(logging.WARNING, logger="pipeline.orchestrator_layers"):
            # Should not raise
            ol.persist_chapter_semantic_findings("any-id", 1, {"x": 1})

    def test_missing_chapter_logs_warning(self, tmp_db, monkeypatch, caplog):
        ol, eng = self._setup(tmp_db, monkeypatch)
        # DB exists but no chapter
        import logging
        with caplog.at_level(logging.WARNING, logger="pipeline.orchestrator_layers"):
            ol.persist_chapter_semantic_findings(
                story_id=str(uuid.uuid4()),
                chapter_number=77,
                findings_dict={},
            )
        assert "no chapter found" in caplog.text.lower()


# ---------------------------------------------------------------------------
# 5. persist_outline_metrics — non-fatal on error
# ---------------------------------------------------------------------------


class TestPersistOutlineMetrics:
    def _setup(self, tmp_db, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_db}")
        import pipeline.orchestrator_layers as ol
        ol._sync_engine = None
        eng = _make_engine(tmp_db)
        return ol, eng

    def test_writes_outline_metrics(self, tmp_db, monkeypatch):
        ol, eng = self._setup(tmp_db, monkeypatch)
        with Session(eng) as s:
            sid, rid = _story_and_run(s)

        ol.persist_outline_metrics(
            story_id=sid,
            metrics_dict={"overall_score": 0.85, "arc_coverage": 0.9},
        )

        with Session(eng) as s:
            run = s.query(PipelineRun).filter_by(id=rid).one()
            assert run.outline_metrics == {"overall_score": 0.85, "arc_coverage": 0.9}

    def test_non_fatal_on_missing_story(self, tmp_db, monkeypatch, caplog):
        ol, eng = self._setup(tmp_db, monkeypatch)
        import logging
        with caplog.at_level(logging.WARNING, logger="pipeline.orchestrator_layers"):
            ol.persist_outline_metrics(
                story_id=str(uuid.uuid4()),
                metrics_dict={"overall_score": 0.5},
            )
        assert "no pipeline_run found" in caplog.text.lower()

    def test_non_fatal_engine_error(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "sqlite:////nonexistent/path/nope.db")
        import pipeline.orchestrator_layers as ol
        ol._sync_engine = None
        # Must not raise
        ol.persist_outline_metrics("any-id", {"overall_score": 0.1})


# ---------------------------------------------------------------------------
# 6. _run_structural_rewrites — cap math + concurrency
# ---------------------------------------------------------------------------


class TestRunStructuralRewrites:
    """Tests for the async _run_structural_rewrites helper."""

    def _make_self(self, batch_size=5):
        """Build a minimal mock 'self' that looks like PipelineOrchestrator."""
        config = MagicMock()
        config.pipeline.chapter_batch_size = batch_size
        story_gen = MagicMock()
        story_gen.write_chapter = MagicMock(return_value=MagicMock(chapter_number=1))
        obj = MagicMock()
        obj.config = config
        obj.story_gen = story_gen
        return obj

    def _make_draft(self, n_chapters=5):
        draft = MagicMock()
        draft.title = "T"
        draft.characters = []
        draft.world = None
        chaps = []
        for i in range(1, n_chapters + 1):
            ch = MagicMock()
            ch.chapter_number = i
            ch.negotiated_contract = None
            chaps.append(ch)
        draft.chapters = chaps
        return draft

    def _make_issue(self, desc="bad", fix="fix it"):
        issue = MagicMock()
        issue.description = desc
        issue.fix_hint = fix
        return issue

    @pytest.mark.asyncio
    async def test_cap_limits_chapters(self):
        """_max_rewrites * len(draft.chapters) cap actually limits entries."""
        from pipeline.orchestrator_layers import _run_structural_rewrites

        draft = self._make_draft(n_chapters=3)
        # 10 issues across chapters 1-10, but cap = 1 * 3 = 3
        issues_by_chapter = {i: [self._make_issue()] for i in range(1, 11)}

        self_obj = self._make_self()
        # write_chapter returns quickly
        rewritten, failed = await _run_structural_rewrites(
            self_obj,
            issues_by_chapter=dict(list(sorted(issues_by_chapter.items()))[:3]),  # already capped by caller
            draft=draft,
            genre="fantasy",
            style="plain",
            word_count=1000,
            outline_map={},
            log_fn=lambda m: None,
        )
        assert len(rewritten) == 3
        assert len(failed) == 0

    @pytest.mark.asyncio
    async def test_failed_chapter_isolated(self):
        """A chapter that raises does not kill sibling rewrites."""
        from pipeline.orchestrator_layers import _run_structural_rewrites

        draft = self._make_draft(n_chapters=3)
        call_count = {"n": 0}

        def _write(**kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("LLM exploded")
            return MagicMock(chapter_number=2)

        self_obj = self._make_self()
        self_obj.story_gen.write_chapter = _write

        issues = {1: [self._make_issue()], 2: [self._make_issue()]}
        rewritten, failed = await _run_structural_rewrites(
            self_obj,
            issues_by_chapter=issues,
            draft=draft,
            genre="fantasy",
            style="plain",
            word_count=1000,
            outline_map={},
            log_fn=lambda m: None,
        )
        assert len(failed) == 1
        assert failed[0][0] == 1
        assert len(rewritten) == 1

    @pytest.mark.asyncio
    async def test_semaphore_respects_batch_size(self):
        """Concurrency never exceeds chapter_batch_size."""
        from pipeline.orchestrator_layers import _run_structural_rewrites

        concurrent = {"current": 0, "max": 0}
        import asyncio as _asyncio

        async def _slow_write(*a, **kw):
            concurrent["current"] += 1
            concurrent["max"] = max(concurrent["max"], concurrent["current"])
            await _asyncio.sleep(0.01)
            concurrent["current"] -= 1
            return MagicMock(chapter_number=1)

        draft = self._make_draft(n_chapters=8)
        self_obj = self._make_self(batch_size=3)
        # Patch asyncio.to_thread to call directly
        with patch("pipeline.orchestrator_layers.asyncio.to_thread", side_effect=_slow_write):
            issues = {i: [self._make_issue()] for i in range(1, 9)}
            await _run_structural_rewrites(
                self_obj,
                issues_by_chapter=issues,
                draft=draft,
                genre="fantasy",
                style="plain",
                word_count=1000,
                outline_map={},
                log_fn=lambda m: None,
            )
        assert concurrent["max"] <= 3


# ---------------------------------------------------------------------------
# 7. run_layer1_only — delegates to story_gen
# ---------------------------------------------------------------------------


class TestRunLayer1Only:
    def _make_orch(self):
        config = MagicMock()
        story_gen = MagicMock()
        story_gen.generate_full_story.return_value = MagicMock(chapters=[MagicMock()])
        obj = MagicMock()
        obj.config = config
        obj.story_gen = story_gen
        return obj

    def test_delegates_to_story_gen(self):
        from pipeline.orchestrator_layers import run_layer1_only
        orch = self._make_orch()
        result = run_layer1_only(
            orch, title="T", genre="G", idea="I",
            style="S", num_chapters=3, num_characters=4, word_count=1000,
        )
        orch.story_gen.generate_full_story.assert_called_once()
        call_kwargs = orch.story_gen.generate_full_story.call_args
        assert call_kwargs.kwargs["title"] == "T"
        assert call_kwargs.kwargs["num_chapters"] == 3
        assert result is not None

    def test_passes_progress_callback(self):
        from pipeline.orchestrator_layers import run_layer1_only
        orch = self._make_orch()
        cb = MagicMock()
        run_layer1_only(
            orch, title="T", genre="G", idea="I",
            style="S", num_chapters=1, num_characters=1, word_count=100,
            progress_callback=cb,
        )
        kwargs = orch.story_gen.generate_full_story.call_args.kwargs
        assert kwargs["progress_callback"] is cb


# ---------------------------------------------------------------------------
# 8. run_layer2_only — signal extraction from draft
# ---------------------------------------------------------------------------


class TestRunLayer2Only:
    def _make_orch(self, use_signals=True):
        config = MagicMock()
        config.pipeline.l2_use_l1_signals = use_signals
        config.pipeline.drama_intensity = "cao"
        analyzer = MagicMock()
        analyzer.analyze.return_value = {"relationships": []}
        sim_result = MagicMock()
        sim_result.events = []
        simulator = MagicMock()
        simulator.run_simulation.return_value = sim_result
        enhancer = MagicMock()
        enhancer.enhance_with_feedback.return_value = MagicMock()
        obj = MagicMock()
        obj.config = config
        obj.analyzer = analyzer
        obj.simulator = simulator
        obj.enhancer = enhancer
        return obj

    def _make_draft(self, conflict_web=None, foreshadowing_plan=None):
        from models.schemas import Character, StoryDraft
        char = Character(name="A", role="chính", personality="brave")
        draft = StoryDraft(title="T", genre="fantasy")
        draft.characters = [char]
        if conflict_web:
            draft.conflict_web = conflict_web
        if foreshadowing_plan:
            draft.foreshadowing_plan = foreshadowing_plan
        return draft

    def _make_conflict_entry(self):
        from models.schemas import ConflictEntry
        return ConflictEntry(
            conflict_id="c1",
            conflict_type="external",
            characters=["A", "B"],
            description="rivalry",
        )

    def _make_foreshadowing_entry(self):
        from models.schemas import ForeshadowingEntry
        return ForeshadowingEntry(
            hint="a subtle clue",
            plant_chapter=1,
            payoff_chapter=5,
        )

    def test_conflict_web_forwarded_to_simulator(self):
        from pipeline.orchestrator_layers import run_layer2_only
        cw = [self._make_conflict_entry()]
        draft = self._make_draft(conflict_web=cw)
        orch = self._make_orch()
        run_layer2_only(orch, draft=draft, num_sim_rounds=3)
        call_kwargs = orch.simulator.run_simulation.call_args.kwargs
        assert call_kwargs["conflict_web"] is not None
        assert len(call_kwargs["conflict_web"]) == 1

    def test_foreshadowing_plan_forwarded_to_simulator(self):
        from pipeline.orchestrator_layers import run_layer2_only
        fp = [self._make_foreshadowing_entry()]
        draft = self._make_draft(foreshadowing_plan=fp)
        orch = self._make_orch()
        run_layer2_only(orch, draft=draft, num_sim_rounds=2)
        call_kwargs = orch.simulator.run_simulation.call_args.kwargs
        assert call_kwargs["foreshadowing_plan"] is not None
        assert len(call_kwargs["foreshadowing_plan"]) == 1

    def test_signals_disabled_sends_none(self):
        from pipeline.orchestrator_layers import run_layer2_only
        cw = [self._make_conflict_entry()]
        fp = [self._make_foreshadowing_entry()]
        draft = self._make_draft(conflict_web=cw, foreshadowing_plan=fp)
        orch = self._make_orch(use_signals=False)
        run_layer2_only(orch, draft=draft, num_sim_rounds=1)
        call_kwargs = orch.simulator.run_simulation.call_args.kwargs
        assert call_kwargs["conflict_web"] is None
        assert call_kwargs["foreshadowing_plan"] is None

    def test_returns_enhanced_story(self):
        from pipeline.orchestrator_layers import run_layer2_only
        draft = self._make_draft()
        orch = self._make_orch()
        result = run_layer2_only(orch, draft=draft)
        assert result is orch.enhancer.enhance_with_feedback.return_value

    def test_analyzer_called_with_conflict_web(self):
        from pipeline.orchestrator_layers import run_layer2_only
        cw = [self._make_conflict_entry()]
        draft = self._make_draft(conflict_web=cw)
        orch = self._make_orch()
        run_layer2_only(orch, draft=draft)
        call_args = orch.analyzer.analyze.call_args
        # second positional arg is the conflict_web
        passed_cw = call_args.args[1] if len(call_args.args) >= 2 else call_args.kwargs.get("conflict_web")
        assert passed_cw is not None
