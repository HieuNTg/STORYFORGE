"""The repair loop: collect → plan → rewrite once → verify → accept or revert.

Replaces the four legacy post-write passes (payoff, consistency, pacing, length)
with one bounded loop. The legacy passes stay in the tree and stay reachable —
they are the fallback when the loop runs out of budget with work still to do,
and they are what runs whenever `enable_agentic_repair` is off.

Invariants, in the order they matter:

1. The budget is a hard ceiling. `RepairBudget.spend` refuses rather than
   overspend, and a refusal ends the round.
2. Nothing here is allowed to break chapter generation. Every failure path
   leaves `chapter` exactly as it was found — same as the legacy passes, which
   are non-fatal by design.
3. A candidate is committed only after a deterministic re-measurement says it is
   no worse. No LLM votes on that.
"""

from __future__ import annotations

import logging

from pipeline.layer1_story.repair.collector import (
    collect_findings,
    collect_pacing_finding,
    recheck_findings,
)
from pipeline.layer1_story.repair.executor import execute_repair
from pipeline.layer1_story.repair.findings import (
    RepairBudget,
    RepairFinding,
    RepairOutcome,
    SEVERITY_WEIGHT,
    Severity,
)
from pipeline.layer1_story.repair.planner import plan_repair

logger = logging.getLogger(__name__)


def _min_severity(pipeline_config) -> Severity:
    raw = str(pipeline_config.repair_min_severity).lower()
    try:
        return Severity(raw)
    except ValueError:
        logger.warning("repair_min_severity=%r not recognised; using 'major'", raw)
        return Severity.MAJOR


def _triggering(findings: list[RepairFinding], floor: Severity) -> list[RepairFinding]:
    """Findings severe enough to justify spending a rewrite."""
    bar = SEVERITY_WEIGHT[floor]
    return [f for f in findings if SEVERITY_WEIGHT.get(f.severity, 0.0) >= bar]


def _score(findings: list[RepairFinding]) -> float:
    """Weighted severity total over the re-measurable findings only.

    Findings whose detector cannot be re-run against candidate text (`pacing`,
    `arc`, `critique`) are excluded: including them would compare a fresh
    measurement against a stale one and reject good rewrites at random. They are
    instead carried forward unchanged, so they can never make the loop iterate
    on its own — a pacing finding the verifier cannot clear would otherwise spin
    the loop until the budget ran out.

    No LLM ever votes on this score. That is the line between this loop and a
    self-refine loop (spec §1.3).
    """
    return sum(SEVERITY_WEIGHT.get(f.severity, 1.0) for f in findings if f.recheckable)


def _commit(ctx, content: str) -> None:
    from models.schemas import count_words

    ctx.chapter.content = content
    ctx.chapter.word_count = count_words(content)


def _sync_context(ctx, findings: list[RepairFinding]) -> None:
    """Refresh the warning lists on `story_context` to describe what actually shipped.

    The legacy consistency pass did this too, and for the same reason: the
    warnings were computed against a draft that no longer exists, and later
    chapters read them as context.
    """
    sc = ctx.story_context
    by_source: dict[str, list[str]] = {}
    for f in findings:
        by_source.setdefault(f.source, []).append(f.evidence or f.detail)

    try:
        sc.name_warnings = by_source.get("name", [])
        sc.arc_drift_warnings = []
        if hasattr(sc, "arc_execution_warnings"):
            sc.arc_execution_warnings = []
        # Location warnings live inside world_rule_violations behind a prefix;
        # replace only those, leave genuine world-rule entries alone.
        existing = list(getattr(sc, "world_rule_violations", None) or [])
        sc.world_rule_violations = [
            w for w in existing if not str(w).startswith("[VỊ TRÍ]")
        ] + by_source.get("location", [])
        sc.foreshadowing_payoff_missing = [
            {"hint": h} for h in by_source.get("payoff", [])
        ]
    except Exception as exc:  # never fail a shipped chapter over bookkeeping
        logger.debug("repair context sync failed (non-fatal): %s", exc)


def _run_legacy_passes(ctx) -> None:
    """The pre-repair behaviour, unchanged, in its original order."""
    from pipeline.layer1_story.chapter_payoff_rewrite import (
        _verify_and_rewrite_missing_payoffs,
    )
    from pipeline.layer1_story.chapter_rewrites import (
        _enforce_pacing,
        _rewrite_for_consistency_violations,
    )
    from pipeline.layer1_story.chapter_length_gate import expand_chapter_if_short

    _verify_and_rewrite_missing_payoffs(
        ctx.pipeline_config,
        ctx.llm,
        ctx.chapter,
        ctx.outline,
        ctx.story_context,
        ctx.foreshadowing_plan,
        ctx.layer_model,
        ctx.progress_callback,
        draft=ctx.draft,
    )
    _rewrite_for_consistency_violations(
        ctx.pipeline_config,
        ctx.llm,
        ctx.chapter,
        ctx.outline,
        ctx.story_context,
        ctx.layer_model,
        ctx.progress_callback,
        draft=ctx.draft,
    )
    _enforce_pacing(
        ctx.pipeline_config,
        ctx.llm,
        ctx.chapter,
        ctx.outline,
        ctx.layer_model,
        ctx.progress_callback,
        draft=ctx.draft,
    )
    expand_chapter_if_short(
        ctx.pipeline_config,
        ctx.llm,
        ctx.chapter,
        ctx.outline,
        ctx.word_count,
        ctx.layer_model,
        ctx.progress_callback,
        draft=ctx.draft,
    )


def repair_chapter(ctx) -> RepairOutcome:
    """Run the bounded repair loop over one written chapter.

    Mutates `ctx.chapter` in place when a rewrite is accepted. Returns what
    happened, for the trace. Never raises.
    """
    outcome = RepairOutcome()
    cfg = ctx.pipeline_config

    budget = RepairBudget(
        max_rounds=cfg.repair_max_rounds, max_calls=cfg.repair_budget_calls
    )
    floor = _min_severity(cfg)

    try:
        findings = collect_findings(ctx)
        findings += collect_pacing_finding(ctx, budget)
    except Exception as exc:
        logger.warning(
            "Ch%s repair collection failed (non-fatal): %s", ctx.chapter_number, exc
        )
        outcome.calls_used = budget.calls_used
        return outcome

    # The critique stash has been consumed; drop it so the next chapter cannot
    # inherit this one's craft notes.
    try:
        if getattr(ctx.story_context, "repair_pending_critique", None) is not None:
            ctx.story_context.repair_pending_critique = None
    except Exception:
        pass

    outcome.findings_before = len(findings)
    if not _triggering(findings, floor):
        outcome.calls_used = budget.calls_used
        outcome.findings_after = len(findings)
        return outcome

    baseline_content = getattr(ctx.chapter, "content", "") or ""
    baseline_words = getattr(ctx.chapter, "word_count", 0)
    carried = [f for f in findings if not f.recheckable]

    # Baseline must be measured with the SAME instrument as the candidate.
    # `findings` above comes from warnings `process_chapter_post_write` computed
    # earlier; `recheck_findings` recomputes them from text. Scoring one against
    # the other compares a stale measurement to a fresh one and accepts rewrites
    # that are plainly worse. So the baseline gets its own recheck pass — free,
    # since every recheckable detector is LLM-free by construction.
    current_score = _score(recheck_findings(ctx, baseline_content))

    ctx.log(
        f"Ch{ctx.chapter_number}: sửa {len(findings)} lỗi trong 1 lượt viết lại…"
    )

    try:
        while budget.can_continue():
            triggering = _triggering(findings, floor)
            if not triggering:
                break

            budget.start_round()
            plan = plan_repair(findings)
            outcome.strategy = plan.strategy
            if plan.strategy == "skip":
                logger.debug(
                    "Ch%s repair skipped: %s", ctx.chapter_number, plan.skip_reason
                )
                break

            revised = execute_repair(plan, ctx, budget)
            if revised is None:
                break

            after = recheck_findings(ctx, revised) + carried
            after_score = _score(after)

            # Any measurable worsening is rejected. A positive tolerance buys
            # the fixes the score cannot see (pacing, arc, craft).
            if after_score > current_score + float(cfg.repair_regression_tolerance):
                outcome.rolled_back = True
                outcome.findings_after = len(findings)
                ctx.log(
                    f"⚠️ Ch{ctx.chapter_number}: bản viết lại xấu hơn — giữ bản cũ"
                )
                logger.info(
                    "Ch%s repair rollback: score %.1f → %.1f",
                    ctx.chapter_number,
                    current_score,
                    after_score,
                )
                break

            _commit(ctx, revised)
            outcome.applied = True
            current_score = after_score
            findings = after

        outcome.rounds_used = budget.rounds_used
        outcome.calls_used = budget.calls_used
        outcome.findings_after = len(findings)

        if outcome.rolled_back:
            # `_commit` only ever ran on verified-better candidates, so the
            # chapter still holds the last good text. Restore explicitly anyway
            # so the invariant does not depend on the loop's control flow.
            if not outcome.applied:
                ctx.chapter.content = baseline_content
                ctx.chapter.word_count = baseline_words
            return outcome

        remaining = _triggering(findings, floor)
        if remaining and cfg.repair_fallback_to_legacy:
            logger.info(
                "Ch%s repair exhausted with %d finding(s) left — falling back to legacy passes",
                ctx.chapter_number,
                len(remaining),
            )
            outcome.fallback_used = True
            _run_legacy_passes(ctx)
            return outcome

        if outcome.applied:
            _sync_context(ctx, findings)
            ctx.log(
                f"Ch{ctx.chapter_number}: đã sửa xong "
                f"({outcome.findings_before} → {outcome.findings_after} lỗi, "
                f"{outcome.calls_used} lượt gọi)"
            )
        return outcome

    except Exception as exc:
        logger.warning(
            "Ch%s repair loop failed (non-fatal): %s", ctx.chapter_number, exc
        )
        ctx.chapter.content = baseline_content
        ctx.chapter.word_count = baseline_words
        outcome.applied = False
        outcome.rounds_used = budget.rounds_used
        outcome.calls_used = budget.calls_used
        return outcome
