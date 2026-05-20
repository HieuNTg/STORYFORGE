"""Simulation transcript extractor.

Converts a raw `SimulationResult` (or dict-shaped artifact) into the
`SimulationTranscript` shape consumed by the SimulationView UI.

Mapping strategy (no LLM by default):
- Each `AgentPost` → `TranscriptTurn`:
    - `id`           = f"t{round_number:02d}-{idx:03d}"
    - `senderId`     = `agent_name`
    - `senderName`   = `agent_name`
    - `emotion`      = `sentiment` (or empty)
    - `actionDetails`= "" (post action types don't carry stage direction)
    - `speech`       = `content`
- `outcomeSummary`   = newline-joined `drama_suggestions` (capped to 4000 chars)

Pure, sync, no I/O. The optional LLM tagging path is intentionally deferred
(YAGNI — Phase 3 Risk #1 mitigation: fall back to defaults when tagging is
unavailable).
"""

from __future__ import annotations

from typing import Any

from models.schemas import (
    AgentPost,
    SimulationResult,
    SimulationTranscript,
    TranscriptTurn,
)

_SUMMARY_MAX = 4000


def _coerce_post(raw: Any) -> AgentPost | None:
    if isinstance(raw, AgentPost):
        return raw
    if isinstance(raw, dict):
        try:
            return AgentPost.model_validate(raw)
        except Exception:
            return None
    return None


def extract(artifact: Any) -> SimulationTranscript:
    """artifact: SimulationResult | dict | {agent_posts, drama_suggestions} → SimulationTranscript."""
    if isinstance(artifact, SimulationResult):
        posts = artifact.agent_posts
        suggestions = artifact.drama_suggestions
    elif isinstance(artifact, dict):
        posts_raw = artifact.get("agent_posts") or []
        posts = [p for p in (_coerce_post(p) for p in posts_raw) if p is not None]
        suggestions = list(artifact.get("drama_suggestions") or [])
    else:
        return SimulationTranscript()

    logs: list[TranscriptTurn] = []
    for idx, post in enumerate(posts):
        name = (post.agent_name or "").strip() or "narrator"
        logs.append(
            TranscriptTurn(
                id=f"t{post.round_number:02d}-{idx:03d}",
                senderId=name,
                senderName=name,
                emotion=(post.sentiment or "").strip()[:80],
                actionDetails="",
                speech=(post.content or "").strip()[:2000],
            )
        )

    summary = "\n".join(s for s in suggestions if isinstance(s, str) and s.strip())
    if len(summary) > _SUMMARY_MAX:
        summary = summary[: _SUMMARY_MAX - 1] + "…"

    return SimulationTranscript(logs=logs, outcomeSummary=summary)


__all__ = ["extract"]
