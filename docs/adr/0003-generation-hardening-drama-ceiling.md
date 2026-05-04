# ADR 0003 — Drama Ceiling on `NegotiatedChapterContract`

**Status:** Accepted
**Date:** 2026-05-04
**Sprint:** [Sprint 3 — Generation Hardening](../../plans/260504-1356-generation-hardening/README.md)

## Context

Sprint 1 unified `ChapterContract` and `DramaContract` into
`NegotiatedChapterContract`, with the simulator filling `drama_target`
(intended intensity) and `drama_tolerance` (genre-aware acceptable
overshoot). Sprint 2 made the L1→L2 plumbing observable. Generation
*behaviour* still ignores the contract's drama bound, however: the only
site that honours `l2_drama_ceiling=True` is
`pipeline/layer2_enhance/enhancer.py::_apply_contract_validation`
(`enhancer.py:419-509`) — which fires *after* the chapter prose is already
written.

`pipeline/layer1_story/chapter_writer._build_chapter_prompt`
(`chapter_writer.py:160-170`) does not read `drama_target` or
`drama_tolerance` at all. The audit measured ~30-50% of chapter writes
silently overshooting the genre ceiling and relying on post-validation
retries to claw drama back. Each retry is a wasted L1 LLM call; flat
chapters that pass the ceiling check go through unchanged.

To wire the simulator's intent into the chapter writer's prompt, we need
*one* numeric upper bound the prompt can phrase as "do not exceed
N.NN". This ADR captures how we represent that bound on the contract.

## Decision

Add a derived `drama_ceiling: float` field to
`NegotiatedChapterContract`, filled at reconciliation time
(`pipeline/handoff_gate._compute_drama_ceiling`,
`pipeline/handoff_gate.reconcile_contract`):

```python
def _compute_drama_ceiling(target: float, tolerance: float) -> float:
    if target <= 0.0:
        return 0.0
    return min(1.0, target + tolerance)
```

When `drama_target == 0.0` post-reconciliation (no simulator data, or the
simulator pass was skipped), `drama_ceiling` stays at `0.0` and
`reconciliation_warnings += ["drama_ceiling_unset_no_target"]` is emitted
so operators can see the writer prompt fell back to the legacy
no-directive path. A positive target always yields a positive ceiling.

The chapter writer (P2) reads `drama_ceiling` and emits the directive
only when `drama_ceiling > 0` — a single boolean check.

## Tradeoffs

### Derived field on the contract vs. arithmetic-in-the-prompt

Considered: pass `drama_target` and `drama_tolerance` separately into the
prompt and let the LLM compute "ceiling = target + tolerance" itself.
Rejected. LLMs are non-deterministic at single-digit-precision arithmetic
in prompts; we have measured the ceiling drifting by 0.05-0.10 across
runs of the same input. It also burns prompt tokens explaining the rule.
Computing once at reconciliation pins the number, makes the prompt
directive readable in Vietnamese ("kịch tính tối đa 0.65, mục tiêu
0.50"), and keeps the writer-side code one comparison.

### Stored derived field vs. computed-on-read property

Considered: expose `drama_ceiling` as a `@computed_field` Pydantic
property derived live from `drama_target + drama_tolerance`. Rejected for
two reasons:

1. **Persistence semantics.** `pipeline_runs.handoff_envelope` stores the
   contract as JSON. A computed field round-trips fine on read but the
   stored value can fall out of sync with the formula if the formula
   itself changes between sprints. Storing the number lets us audit "the
   ceiling that was in effect at generation time" by reading the JSON,
   not by re-running the formula against today's code.
2. **Single-write reconciliation.** All reconciliation effects already
   live in `reconcile_contract`. Adding ceiling computation there keeps
   the reconciled-vs-pre-reconciled distinction crisp: pre-reconciled
   contracts have `drama_ceiling=0.0`, reconciled contracts have the
   computed value. A computed field would erase that distinction.

### Per-chapter ceiling vs. per-character ceiling

Considered: per-character `drama_ceiling` keyed on `Character.id`, so a
brooding-stoic protagonist gets a tighter ceiling than the antagonist.
Rejected for Sprint 3:

- The simulator currently produces one `drama_target` per chapter, not
  per character. A per-character ceiling needs per-character target,
  which is a simulator-side change out of scope for this sprint
  (Non-goal #1 in `README.md`).
- Voice fingerprints already capture per-character intensity preferences
  via `emotional_baseline` and `verbal_tics`. The chapter-level ceiling
  bounds the *scene*, not the individual line. Speaker-level moderation
  is a Sprint 4+ concern (deferred to "Out of scope" in `README.md`).
- One number per chapter is the minimum useful signal that wires
  simulator intent into writer prompt. Per-character bounds add three
  fields and a lookup without solving the present overshoot problem.

### Clamp at 1.0 vs. allow-overshoot

`min(1.0, target + tolerance)` clips at the schema's upper bound. A
target of 0.95 with tolerance 0.20 yields ceiling 1.0 (capped), not 1.15.
The Pydantic field declares `le=1.0` so any uncapped value would fail
validation; the clamp is the contract.

### Sentinel `target == 0.0 → ceiling == 0.0`

This is the "no simulator data" sentinel. A naive
`min(1.0, 0.0 + 0.15)` would yield `0.15` — a ceiling on a chapter the
simulator never scored. The chapter writer would then emit the directive
("trần 0.15") which is meaningless. Returning `0.0` lets the writer
detect "no contract data" via `drama_ceiling > 0` and skip the directive
entirely, preserving zero-diff behaviour for legacy paths and unit tests
that don't run the simulator.

## Consequences

**Easier:**
- Chapter writer prompt directive (P2) becomes a single
  `if contract.drama_ceiling > 0:` check; no arithmetic in the prompt
  builder, no two-field plumbing.
- The same ceiling is read by writer (P2), structural rewrite path (P2),
  and post-validation (`enhancer.py`), so the four sites cannot diverge.
- `reconciliation_warnings` carries `drama_ceiling_unset_no_target` for
  operators tracking "did the simulator actually produce data for this
  chapter?" — visible from the diagnostics endpoint without recomputing.
- Stored on `pipeline_runs.handoff_envelope` JSON automatically; legacy
  rows have no `drama_ceiling` key, default `0.0` makes them load as
  `extra="forbid"` is already on.

**Harder:**
- Adding more derived contract fields in future sprints follows this
  pattern (compute in `reconcile_contract`, default-zero sentinel on the
  schema). Discipline required: don't add live `@computed_field`
  properties on `NegotiatedChapterContract` without revisiting the
  persistence-semantics tradeoff above.
- One additional reconciliation warning (`drama_ceiling_unset_no_target`)
  fires on any contract that goes through `reconcile_contract` without
  simulator data — including legacy unit tests that build contracts with
  default `drama_target=0.0`. Tests that assert `reconciliation_warnings
  == []` for a setup-pacing-target-zero contract need updating. This is
  the intentional cost of making the "no data" case observable.

## References

- Plan: [`plans/260504-1356-generation-hardening/README.md`](../../plans/260504-1356-generation-hardening/README.md)
- Schema: [`plans/260504-1356-generation-hardening/schema.md`](../../plans/260504-1356-generation-hardening/schema.md) §1
- Phases: [`plans/260504-1356-generation-hardening/phases.md`](../../plans/260504-1356-generation-hardening/phases.md) P1
- Sprint 1 ADR (contract unification): [`0001-l1-handoff-envelope.md`](0001-l1-handoff-envelope.md)
