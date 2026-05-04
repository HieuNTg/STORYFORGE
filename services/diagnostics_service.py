"""Diagnostics service — build handoff health summary for a story.

Reads from pipeline_runs.handoff_envelope / handoff_health and
chapters.negotiated_contract / contract_reconciliation_warnings.

Pre-migration rows (NULL columns) return None, which the API route
converts to 404.
"""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

_DB_URL = os.environ.get("DATABASE_URL", "sqlite:///data/storyforge.db")


def _sync_engine():
    from sqlalchemy import create_engine
    connect_args = {"check_same_thread": False} if "sqlite" in _DB_URL else {}
    return create_engine(_DB_URL, connect_args=connect_args)


def build_handoff_diagnostics(story_id: str) -> dict | None:
    """Return handoff diagnostics for *story_id*, or None if not found / pre-migration.

    Shape:
        {
            "story_id": str,
            "envelope": dict | None,          # L1Handoff serialised
            "signal_health_summary": {         # aggregated from envelope.signal_health
                "<signal>": {"status": str, "item_count": int, "reason": str|null}
            },
            "signals_ok": int,                 # count of status=="ok"
            "signals_total": int,
            "per_chapter_contracts": [         # one entry per chapter with negotiated_contract
                {
                    "chapter_number": int,
                    "pacing_type": str,
                    "drama_target": float,
                    "reconciled": bool,
                    "reconciliation_warnings": list[str],
                }
            ],
        }
    """
    from sqlalchemy import text

    engine = _sync_engine()
    try:
        with engine.connect() as conn:
            # 1. Find the story
            story_row = conn.execute(
                text("SELECT id FROM stories WHERE id = :sid"),
                {"sid": story_id},
            ).fetchone()
            if story_row is None:
                return None

            # 2. Find the most recent pipeline_run for this story that has a handoff_envelope
            run_row = conn.execute(
                text(
                    "SELECT handoff_envelope, handoff_health, handoff_signals_version "
                    "FROM pipeline_runs "
                    "WHERE story_id = :sid AND handoff_envelope IS NOT NULL "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"sid": story_id},
            ).fetchone()

            # Pre-migration story: no handoff data at all
            if run_row is None:
                return None

            envelope = run_row[0]  # JSON column; str on SQLite, dict on PG JSONB
            health_raw = run_row[1]  # may be None

            # Normalise: SQLite stores JSON as TEXT; parse if needed.
            if isinstance(envelope, str):
                envelope = json.loads(envelope)
            if isinstance(health_raw, str):
                health_raw = json.loads(health_raw)

            # 3. Build signal health summary
            signal_health_summary: dict = {}
            signals_ok = 0
            if isinstance(envelope, dict) and isinstance(envelope.get("signal_health"), dict):
                for sig, h in envelope["signal_health"].items():
                    if not isinstance(h, dict):
                        continue
                    signal_health_summary[sig] = {
                        "status": h.get("status", "unknown"),
                        "item_count": h.get("item_count", 0),
                        "reason": h.get("reason"),
                    }
                    if h.get("status") == "ok":
                        signals_ok += 1
            elif isinstance(health_raw, dict):
                # Fallback: use persisted handoff_health if envelope missing signal_health
                for sig, h in health_raw.items():
                    if not isinstance(h, dict):
                        continue
                    signal_health_summary[sig] = {
                        "status": h.get("status", "unknown"),
                        "item_count": h.get("item_count", 0),
                        "reason": h.get("reason"),
                    }
                    if h.get("status") == "ok":
                        signals_ok += 1

            signals_total = len(signal_health_summary)

            # 4. Fetch chapter contracts
            ch_rows = conn.execute(
                text(
                    "SELECT chapter_number, negotiated_contract, contract_reconciliation_warnings "
                    "FROM chapters WHERE story_id = :sid ORDER BY chapter_number"
                ),
                {"sid": story_id},
            ).fetchall()

            per_chapter: list[dict] = []
            for ch_row in ch_rows:
                ch_num = ch_row[0]
                contract = ch_row[1]
                warnings = ch_row[2]
                # Normalise: SQLite stores JSON as TEXT.
                if isinstance(contract, str):
                    contract = json.loads(contract)
                if isinstance(warnings, str):
                    try:
                        warnings = json.loads(warnings)
                    except (ValueError, TypeError):
                        warnings = None
                if not isinstance(contract, dict):
                    continue
                per_chapter.append({
                    "chapter_number": ch_num,
                    "pacing_type": contract.get("pacing_type", ""),
                    "drama_target": contract.get("drama_target", 0.0),
                    "reconciled": bool(contract.get("reconciled", False)),
                    "reconciliation_warnings": list(
                        warnings if isinstance(warnings, list)
                        else contract.get("reconciliation_warnings", [])
                    ),
                })

            return {
                "story_id": story_id,
                "envelope": envelope,
                "signal_health_summary": signal_health_summary,
                "signals_ok": signals_ok,
                "signals_total": signals_total,
                "per_chapter_contracts": per_chapter,
            }
    except Exception as exc:
        logger.warning("build_handoff_diagnostics failed for story_id=%s: %s", story_id, exc)
        return None
    finally:
        engine.dispose()


def build_semantic_diagnostics(story_id: str) -> dict | None:
    """Return semantic diagnostics for *story_id*, or None if not found / pre-Sprint-2.

    Shape:
        {
            "story_id": str,
            "outline_metrics": dict | None,    # OutlineMetrics dump from pipeline_runs
            "per_chapter": [                   # one entry per chapter with findings
                {
                    "chapter_num": int,
                    "semantic_findings": dict | None,      # ChapterSemanticFindings dump
                    "contract": dict | None,               # NegotiatedChapterContract dump
                }
            ],
            "summary": {
                "total_payoff_matched": int,
                "total_payoff_weak": int,
                "total_payoff_missed": int,
                "total_structural_findings_by_severity": {
                    "critical": int,    # severity >= 0.80
                    "major": int,       # 0.60 <= severity < 0.80
                    "minor": int,       # severity < 0.60
                },
                "outline_floors_violated": list[str],
            },
        }

    Returns None when the story does not exist or has no Sprint-2 data at all
    (i.e., both semantic_findings columns and outline_metrics are NULL).
    """
    from sqlalchemy import text

    engine = _sync_engine()
    try:
        with engine.connect() as conn:
            # 1. Verify story exists
            story_row = conn.execute(
                text("SELECT id FROM stories WHERE id = :sid"),
                {"sid": story_id},
            ).fetchone()
            if story_row is None:
                return None

            # 2. Fetch most recent outline_metrics from pipeline_runs
            run_row = conn.execute(
                text(
                    "SELECT outline_metrics FROM pipeline_runs "
                    "WHERE story_id = :sid AND outline_metrics IS NOT NULL "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"sid": story_id},
            ).fetchone()

            outline_metrics: dict | None = None
            if run_row is not None:
                om = run_row[0]
                if isinstance(om, str):
                    om = json.loads(om)
                if isinstance(om, dict):
                    outline_metrics = om

            # 3. Fetch per-chapter semantic findings + contracts
            ch_rows = conn.execute(
                text(
                    "SELECT chapter_number, semantic_findings, negotiated_contract "
                    "FROM chapters WHERE story_id = :sid ORDER BY chapter_number"
                ),
                {"sid": story_id},
            ).fetchall()

            # Pre-Sprint-2: no findings and no outline_metrics → return None
            has_any_findings = any(row[1] is not None for row in ch_rows)
            if outline_metrics is None and not has_any_findings:
                return None

            per_chapter: list[dict] = []
            for ch_row in ch_rows:
                ch_num = ch_row[0]
                findings_raw = ch_row[1]
                contract_raw = ch_row[2]

                # Normalise JSON columns — SQLite returns TEXT
                if isinstance(findings_raw, str):
                    try:
                        findings_raw = json.loads(findings_raw)
                    except (ValueError, TypeError):
                        findings_raw = None
                if isinstance(contract_raw, str):
                    try:
                        contract_raw = json.loads(contract_raw)
                    except (ValueError, TypeError):
                        contract_raw = None

                per_chapter.append({
                    "chapter_num": ch_num,
                    "semantic_findings": findings_raw if isinstance(findings_raw, dict) else None,
                    "contract": contract_raw if isinstance(contract_raw, dict) else None,
                })

            # 4. Build summary
            total_matched = 0
            total_weak = 0
            total_missed = 0
            total_critical = 0
            total_major = 0
            total_minor = 0

            for ch in per_chapter:
                sf = ch.get("semantic_findings")
                if not isinstance(sf, dict):
                    continue
                for pm in sf.get("payoff_matches", []):
                    if not isinstance(pm, dict):
                        continue
                    conf = pm.get("confidence", 0.0)
                    threshold = pm.get("threshold_used", 0.62)
                    matched = pm.get("matched", False)
                    if matched:
                        total_matched += 1
                    elif conf >= max(0.0, threshold - 0.05):
                        total_weak += 1
                    else:
                        total_missed += 1
                for sf_item in sf.get("structural_findings", []):
                    if not isinstance(sf_item, dict):
                        continue
                    sev = sf_item.get("severity", 0.0)
                    if sev >= 0.80:
                        total_critical += 1
                    elif sev >= 0.60:
                        total_major += 1
                    else:
                        total_minor += 1

            # Determine floors violated from outline_metrics
            outline_floors_violated: list[str] = []
            if isinstance(outline_metrics, dict):
                _floors = {
                    "conflict_web_density": 0.10,
                    "arc_trajectory_variance": 0.10,
                    "pacing_distribution_skew": 0.30,
                    "beat_coverage_ratio": 0.50,
                    "character_screen_time_gini": None,  # gini floor checked as balance
                }
                _balance_floor = 0.30
                if outline_metrics.get("character_screen_time_gini") is not None:
                    balance = 1.0 - outline_metrics["character_screen_time_gini"]
                    if balance < _balance_floor:
                        outline_floors_violated.append("character_screen_time_balance")
                for field, floor in _floors.items():
                    if floor is None:
                        continue
                    val = outline_metrics.get(field)
                    if val is not None and val < floor:
                        outline_floors_violated.append(field)

            return {
                "story_id": story_id,
                "outline_metrics": outline_metrics,
                "per_chapter": per_chapter,
                "summary": {
                    "total_payoff_matched": total_matched,
                    "total_payoff_weak": total_weak,
                    "total_payoff_missed": total_missed,
                    "total_structural_findings_by_severity": {
                        "critical": total_critical,
                        "major": total_major,
                        "minor": total_minor,
                    },
                    "outline_floors_violated": outline_floors_violated,
                },
            }
    except Exception as exc:
        logger.warning("build_semantic_diagnostics failed for story_id=%s: %s", story_id, exc)
        return None
    finally:
        engine.dispose()
