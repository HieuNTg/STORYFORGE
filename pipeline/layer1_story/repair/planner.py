"""Decide what to do about a set of findings.

Deterministic: gather every finding, carry every constraint, rewrite once. Zero
LLM calls, and it already delivers the two things the loop exists for — one
regeneration instead of five, and no fix silently undone by the next pass.
"""

from __future__ import annotations

from pipeline.layer1_story.repair.findings import (
    RepairFinding,
    RepairPlan,
    SEVERITY_WEIGHT,
)

# Ordering for the rewrite instruction list. Blockers first so that when the
# model has to trade one instruction against another, it sacrifices the least
# important one — and the prompt tells it to prefer the earlier constraint.
_SOURCE_PRIORITY = {
    "payoff": 0,
    "location": 1,
    "name": 2,
    "arc": 3,
    "pacing": 4,
    "length": 5,
    "critique": 6,
}


def _sort_key(f: RepairFinding) -> tuple:
    return (
        -SEVERITY_WEIGHT.get(f.severity, 0.0),
        _SOURCE_PRIORITY.get(f.source, 99),
        f.detail,
    )


def plan_repair(findings: list[RepairFinding]) -> RepairPlan:
    """One unified rewrite carrying every constraint."""
    if not findings:
        return RepairPlan(strategy="skip", skip_reason="no findings")

    ordered = sorted(findings, key=_sort_key)

    fixes: list[str] = []
    constraints: list[str] = []
    seen_constraints: set[str] = set()

    for f in ordered:
        line = f.detail
        if f.evidence and f.evidence != f.detail:
            line = f"{line}\n  (dẫn chứng: {f.evidence})"
        fixes.append(line)
        if f.hard_constraint and f.hard_constraint not in seen_constraints:
            seen_constraints.add(f.hard_constraint)
            constraints.append(f.hard_constraint)

    return RepairPlan(
        strategy="full_rewrite", ordered_fixes=fixes, constraints=constraints
    )
