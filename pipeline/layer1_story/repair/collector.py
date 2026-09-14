"""Turn the existing L1 detectors into a flat list of `RepairFinding`.

Two entry points, and the difference between them matters:

* `collect_findings(ctx)` reads what `process_chapter_post_write` already
  computed onto `story_context`. Free — no detector re-runs, no LLM calls.
  This is what the loop starts from.

* `recheck_findings(ctx, content)` re-measures a *candidate* rewrite. It re-runs
  only the detectors that read chapter text and cost nothing
  (`RECHECKABLE_SOURCES`), and it must not touch `story_context` — the candidate
  may still be rejected.

Neither function mutates `story_context`. That is the contract the whole loop
rests on, and `test_collector_is_pure` enforces it.
"""

from __future__ import annotations

import copy
import logging
from types import SimpleNamespace

from pipeline.layer1_story.repair.findings import RepairFinding, Severity

logger = logging.getLogger(__name__)

# Location warnings are stored inside `world_rule_violations` behind this prefix
# (see post_processing.py) — the same filter `chapter_rewrites` uses.
_LOCATION_PREFIX = "[VỊ TRÍ]"

_EVIDENCE_MAX = 300


def _trim(text: str, limit: int = _EVIDENCE_MAX) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _cfg(ctx, name: str):
    """Read a pipeline config field. Config defaults live in config/defaults.py."""
    return getattr(ctx.pipeline_config, name)


# ---------------------------------------------------------------------------
# Individual sources
# ---------------------------------------------------------------------------


def _payoff_findings(ctx, missing: list | None) -> list[RepairFinding]:
    """Foreshadowing due this chapter but not detected in the prose."""
    out: list[RepairFinding] = []
    for item in missing or []:
        hint = ""
        plant = ""
        if isinstance(item, dict):
            hint = str(item.get("hint", ""))
            plant = str(item.get("plant_chapter", ""))
        else:
            hint = str(getattr(item, "hint", "") or "")
            plant = str(getattr(item, "plant_chapter", "") or "")
        if not hint:
            continue
        out.append(
            RepairFinding(
                source="payoff",
                severity=Severity.BLOCKER,
                detail=(
                    f"Foreshadowing đến hạn trả trong chương này nhưng chưa được thực hiện: {_trim(hint, 160)}"
                    + (f" (gieo ở chương {plant})" if plant else "")
                ),
                evidence=_trim(hint),
                hard_constraint=(
                    f"Chương PHẢI thực hiện payoff cho foreshadowing: {_trim(hint, 160)} "
                    "— gắn vào hành động/tình tiết, không phải lời thoại thừa."
                ),
            )
        )
    return out


def _name_findings(ctx, warnings: list | None) -> list[RepairFinding]:
    """Character names that drifted from their canonical form."""
    warnings = [str(w) for w in (warnings or []) if str(w).strip()]
    if not warnings:
        return []
    threshold = int(_cfg(ctx, "consistency_name_warning_threshold"))
    # Match legacy trigger semantics: below the threshold these were carried as
    # log lines only, never worth a rewrite on their own.
    severity = Severity.MAJOR if len(warnings) >= threshold else Severity.MINOR
    return [
        RepairFinding(
            source="name",
            severity=severity,
            detail=f"Tên nhân vật sai dạng chuẩn: {_trim(w, 200)}",
            evidence=_trim(w),
            hard_constraint="Dùng đúng dạng chuẩn của mọi tên nhân vật đã nêu.",
        )
        for w in warnings
    ]


def _arc_findings(ctx, warnings: list | None) -> list[RepairFinding]:
    """Character arc drift / a planned arc stage the chapter never executed.

    Not recheckable: `detect_arc_drift` reads `character_states`, not prose.
    """
    warnings = [str(w) for w in (warnings or []) if str(w).strip()]
    if not warnings:
        return []
    threshold = int(_cfg(ctx, "consistency_arc_drift_threshold"))
    severity = Severity.MAJOR if len(warnings) >= threshold else Severity.MINOR
    return [
        RepairFinding(
            source="arc",
            severity=severity,
            detail=f"Arc nhân vật lệch tiến trình: {_trim(w, 200)}",
            evidence=_trim(w),
            hard_constraint="Điều chỉnh arc position của nhân vật cho khớp tiến trình truyện.",
        )
        for w in warnings
    ]


def _location_findings(ctx, violations: list | None) -> list[RepairFinding]:
    """Impossible/unexplained location transitions."""
    warnings = [
        str(w) for w in (violations or []) if str(w).startswith(_LOCATION_PREFIX)
    ]
    if not warnings:
        return []
    threshold = int(_cfg(ctx, "consistency_location_warning_threshold"))
    severity = Severity.MAJOR if len(warnings) >= threshold else Severity.MINOR
    return [
        RepairFinding(
            source="location",
            severity=severity,
            detail=f"Chuyển cảnh/vị trí không hợp lý: {_trim(w, 200)}",
            evidence=_trim(w),
            hard_constraint="Bổ sung chi tiết di chuyển để chuyển cảnh hợp lý.",
        )
        for w in warnings
    ]


def _length_finding(ctx, content: str) -> list[RepairFinding]:
    """Chapter materially under the requested word count.

    Severity is MAJOR, not MINOR: the legacy length gate spends a full chapter
    regeneration on this, so it has to clear `repair_min_severity` on its own or
    enabling repair would silently stop expanding short chapters.
    """
    target = int(ctx.word_count or 0)
    if not _cfg(ctx, "enable_length_gate") or target <= 0 or not content:
        return []
    from models.schemas import count_words

    current = count_words(content)
    ratio = float(_cfg(ctx, "length_gate_min_ratio"))
    floor = int(target * ratio)
    if current >= floor:
        return []
    return [
        RepairFinding(
            source="length",
            severity=Severity.MAJOR,
            detail=(
                f"Chương chỉ có {current}/{target} từ "
                f"({100.0 * current / target:.0f}% mục tiêu) — thiếu khoảng {target - current} từ."
            ),
            hard_constraint=(
                f"Chương PHẢI dài ít nhất {floor} từ (mục tiêu {target}). "
                "Bổ sung bằng cảnh diễn ra trực tiếp, đối thoại, nội tâm — không kéo dài lê thê, "
                "không lặp ý đã viết."
            ),
        )
    ]


def _pacing_finding(ctx, verdict: dict | None) -> list[RepairFinding]:
    """Pacing classifier disagreed with the outline's pacing_type."""
    if not verdict or verdict.get("match", True):
        return []
    confidence = float(verdict.get("confidence", 0.0) or 0.0)
    if confidence < float(_cfg(ctx, "pacing_enforcement_confidence")):
        return []
    target = (getattr(ctx.outline, "pacing_type", "") or "").strip().lower()
    detected = str(verdict.get("detected", "") or "")
    return [
        RepairFinding(
            source="pacing",
            severity=Severity.MAJOR,
            detail=(
                f"Nhịp chương lệch: outline yêu cầu '{target}', thực tế đọc ra '{detected}' "
                f"(confidence {confidence:.2f}). Lý do: {_trim(str(verdict.get('reason', '')), 200)}"
            ),
            evidence=_trim(str(verdict.get("reason", ""))),
            hard_constraint=f"Nhịp chương PHẢI khớp '{target}'.",
        )
    ]


def _critique_findings(ctx, critique: dict | None) -> list[RepairFinding]:
    """Weak sections named by the self-critique pass.

    MINOR by design: this is the model grading its own prose, the one signal the
    spec refuses to treat as a loop condition (§1.3). Useful as instruction for
    a rewrite that is happening anyway; never a reason to start one.
    """
    if not isinstance(critique, dict):
        return []
    out: list[RepairFinding] = []
    for section in critique.get("weak_sections") or []:
        if not isinstance(section, dict):
            continue
        issue = str(section.get("issue", "") or "").strip()
        if not issue:
            continue
        location = str(section.get("location", "") or "").strip() or "toàn chương"
        out.append(
            RepairFinding(
                source="critique",
                severity=Severity.MINOR,
                detail=f"Phần {location} còn yếu: {_trim(issue, 200)}",
                evidence=_trim(issue),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def collect_findings(ctx) -> list[RepairFinding]:
    """Gather findings from state `process_chapter_post_write` already produced.

    Zero detector re-runs and zero LLM calls. Does not mutate `story_context`;
    the pending critique stash is read but left in place for the caller to clear.
    """
    sc = ctx.story_context
    findings: list[RepairFinding] = []

    findings += _payoff_findings(ctx, getattr(sc, "foreshadowing_payoff_missing", None))
    findings += _name_findings(ctx, getattr(sc, "name_warnings", None))

    arc_warnings = list(getattr(sc, "arc_drift_warnings", None) or []) + list(
        getattr(sc, "arc_execution_warnings", None) or []
    )
    findings += _arc_findings(ctx, arc_warnings)
    findings += _location_findings(ctx, getattr(sc, "world_rule_violations", None))
    findings += _length_finding(ctx, getattr(ctx.chapter, "content", "") or "")
    findings += _critique_findings(ctx, getattr(sc, "repair_pending_critique", None))

    return findings


def collect_pacing_finding(ctx, budget) -> list[RepairFinding]:
    """Run the pacing classifier — the one detector that costs an LLM call.

    Called once, before the loop, and only if the budget can afford it. Returns
    `[]` on any failure: repair must never fail over a measurement.
    """
    if not _cfg(ctx, "enable_pacing_enforcement"):
        return []
    if not _cfg(ctx, "pacing_mismatch_rewrite"):
        # Legacy still ran the classifier here just to log "pacing lệch — không
        # rewrite". Spending an LLM call to produce a log line is the kind of
        # work this batch exists to remove, so detection is skipped outright
        # when its only possible outcome is a message.
        return []
    target = (getattr(ctx.outline, "pacing_type", "") or "").strip().lower()
    if not target:
        return []
    if not budget.spend(1):
        return []
    try:
        from pipeline.layer1_story.pacing_enforcer import verify_pacing

        verdict = verify_pacing(
            ctx.llm,
            getattr(ctx.chapter, "content", "") or "",
            target,
            model=ctx.layer_model,
        )
        return _pacing_finding(ctx, verdict)
    except Exception as exc:
        logger.warning("pacing detection failed (non-fatal): %s", exc)
        return []


def recheck_findings(ctx, content: str) -> list[RepairFinding]:
    """Re-measure a candidate rewrite using only free, text-driven detectors.

    Must not mutate `story_context` or any object hanging off it — the candidate
    can still be rejected, and a mutated context would leak the rejected draft's
    measurements into the surviving chapter.
    """
    findings: list[RepairFinding] = []

    # Length — pure.
    findings += _length_finding(ctx, content)

    # Character names — regex over the text, zero cost.
    try:
        from pipeline.layer1_story.consistency_validators import (
            validate_character_names,
        )

        findings += _name_findings(ctx, validate_character_names(content, ctx.characters))
    except Exception as exc:
        logger.debug("name recheck failed (non-fatal): %s", exc)

    # Location transitions — pure Python, but needs the location maps that
    # post-write computed. Without them we cannot re-measure, so we skip rather
    # than guess.
    if ctx.prev_locations is not None and ctx.new_locations is not None:
        try:
            from pipeline.layer1_story.consistency_validators import (
                validate_location_transitions,
            )

            # `validate_location_transitions` already emits the [VỊ TRÍ] prefix.
            warnings = validate_location_transitions(
                ctx.prev_locations, ctx.new_locations, content
            )
            findings += _location_findings(ctx, warnings)
        except Exception as exc:
            logger.debug("location recheck failed (non-fatal): %s", exc)

    # Foreshadowing payoffs — embedding similarity, no LLM. `verify_payoffs`
    # mutates the seeds it is given, so it gets a deep copy and the real plan is
    # left untouched until the candidate is committed.
    findings += _recheck_payoffs(ctx, content)

    return findings


def _recheck_payoffs(ctx, content: str) -> list[RepairFinding]:
    if not ctx.foreshadowing_plan:
        return []
    if not _cfg(ctx, "enable_foreshadowing_payoff_verify"):
        return []
    if not _cfg(ctx, "enable_semantic_foreshadowing"):
        return []
    try:
        from pipeline.layer1_story.foreshadowing_manager import get_payoffs_due
        from pipeline.semantic.foreshadowing_verifier import verify_payoffs

        due = get_payoffs_due(ctx.foreshadowing_plan, ctx.chapter_number)
        if not due:
            return []
        due_copy = copy.deepcopy(due)
        # Not a real `Chapter`: an uncommitted candidate has no valid contract
        # or summary, and the verifier only reads these two fields.
        probe = SimpleNamespace(chapter_number=ctx.chapter_number, content=content)
        threshold = float(_cfg(ctx, "semantic_foreshadowing_threshold"))
        verify_payoffs(due_copy, [probe], threshold=threshold)
        missing = [
            {
                "hint": getattr(p, "hint", ""),
                "confidence": getattr(p, "planted_confidence", 0.0) or 0.0,
                "payoff_chapter": getattr(p, "payoff_chapter", None),
                "plant_chapter": getattr(p, "plant_chapter", None),
            }
            for p in due_copy
            if not getattr(p, "paid_off", False)
        ]
        return _payoff_findings(ctx, missing)
    except Exception as exc:
        logger.debug("payoff recheck failed (non-fatal): %s", exc)
        return []


