"""L1 → L2 handoff validation gate (Sprint 1, Phase 3).

Single chokepoint between Layer 1 and Layer 2. Validates the typed `L1Handoff`
envelope produced by `pipeline/layer1_story/handoff_builder.py`, optionally
fails fast in strict mode, and reconciles `NegotiatedChapterContract` instances
against simulator output.

See `plans/260503-2317-l1-l2-handoff-envelope/schema.md` for reconciliation
rules and `plans/260503-2317-l1-l2-handoff-envelope/README.md` decision D2 for
strict-vs-warn policy.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from models.handoff_schemas import L1Handoff, NegotiatedChapterContract


logger = logging.getLogger("storyforge.handoff_gate")

_STRICT_ENV = "STORYFORGE_HANDOFF_STRICT"
_TRUTHY = {"1", "true", "True", "yes", "on"}

_BLOCKER_STATUSES = ("malformed", "extraction_failed")
_WARNING_STATUSES = ("empty",)


class HandoffValidationError(RuntimeError):
    """Raised in strict mode when the L1 handoff envelope is unusable by L2."""

    def __init__(self, blockers: list[str], envelope: L1Handoff):
        self.blockers = list(blockers)
        self.envelope = envelope
        super().__init__(
            f"L1 handoff blocked by {len(self.blockers)} signal(s): {self.blockers}"
        )


def _is_strict(strict: Optional[bool]) -> bool:
    if strict is not None:
        return bool(strict)
    return os.environ.get(_STRICT_ENV, "") in _TRUTHY


def validate_handoff(envelope: L1Handoff) -> tuple[bool, list[str], list[str]]:
    """Returns (ok, blockers, warnings).

    - blockers: signal names whose status is `malformed` or `extraction_failed`.
    - warnings: signal names whose status is `empty` (informational only).
    """
    blockers: list[str] = []
    warnings: list[str] = []
    for name, health in envelope.signal_health.items():
        if health.status in _BLOCKER_STATUSES:
            blockers.append(name)
        elif health.status in _WARNING_STATUSES:
            warnings.append(name)
    return (len(blockers) == 0, blockers, warnings)


def enforce_handoff(
    envelope: L1Handoff,
    *,
    strict: Optional[bool] = None,
) -> L1Handoff:
    """Strict mode: raises `HandoffValidationError` on blockers.

    Default mode: logs a structured warning and returns the envelope unchanged.
    `strict=None` reads `STORYFORGE_HANDOFF_STRICT` from env (truthy → strict).
    """
    ok, blockers, warnings = validate_handoff(envelope)
    total = len(envelope.signal_health)
    ok_count = total - len(blockers) - len(warnings)

    if ok and not warnings:
        logger.info(
            "handoff_validated story_id=%s signals_ok=%d/%d",
            envelope.story_id, ok_count, total,
        )
        return envelope

    if not ok and _is_strict(strict):
        logger.error(
            "handoff_blocked story_id=%s blockers=%s warnings=%s",
            envelope.story_id, blockers, warnings,
        )
        raise HandoffValidationError(blockers, envelope)

    logger.warning(
        "handoff_degraded story_id=%s blockers=%s warnings=%s",
        envelope.story_id, blockers, warnings,
    )
    return envelope


def _compute_drama_ceiling(target: float, tolerance: float) -> float:
    if target <= 0.0:
        return 0.0
    return min(1.0, target + tolerance)


def reconcile_contract(
    contract: NegotiatedChapterContract,
    sim_result: Optional[dict] = None,  # noqa: ARG001 — reserved for future signal cross-checks
) -> NegotiatedChapterContract:
    """Apply pacing/drama clamp rules from `schema.md`.

    Returns a NEW contract; never mutates input. Sets `reconciled=True` and
    accumulates `reconciliation_warnings`. Deterministic — no LLM, no randomness.
    """
    warnings: list[str] = list(contract.reconciliation_warnings)
    drama_target = contract.drama_target

    if contract.pacing_type == "cooldown" and drama_target > 0.6:
        warnings.append(
            f"cooldown chapter {contract.chapter_num}: drama_target {drama_target:.2f} "
            f"clamped to 0.40"
        )
        drama_target = 0.4

    if contract.pacing_type == "climax" and drama_target < 0.7:
        warnings.append(
            f"climax chapter {contract.chapter_num}: drama_target {drama_target:.2f} "
            f"raised to 0.75"
        )
        drama_target = 0.75

    if contract.payoffs_required and not any(
        ref in contract.causal_refs for ref in contract.payoffs_required
    ):
        warnings.append(
            f"chapter {contract.chapter_num}: payoffs_required={contract.payoffs_required} "
            f"have no matching causal_refs"
        )

    drama_ceiling = _compute_drama_ceiling(drama_target, contract.drama_tolerance)
    if drama_target == 0.0:
        warnings.append("drama_ceiling_unset_no_target")

    return contract.model_copy(
        update={
            "drama_target": drama_target,
            "drama_ceiling": drama_ceiling,
            "reconciled": True,
            "reconciliation_warnings": warnings,
        }
    )
