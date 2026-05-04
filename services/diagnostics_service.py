"""Diagnostics service — build handoff health summary for a story.

Reads from pipeline_runs.handoff_envelope / handoff_health and
chapters.negotiated_contract / contract_reconciliation_warnings.

Pre-migration rows (NULL columns) return None, which the API route
converts to 404.
"""

from __future__ import annotations

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

            envelope = run_row[0]  # JSON column, already dict
            health_raw = run_row[1]  # may be None

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
