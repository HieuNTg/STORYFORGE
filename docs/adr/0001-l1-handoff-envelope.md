# ADR 0001 — L1 → L2 Handoff Envelope

**Status:** Accepted
**Date:** 2026-05-04
**Sprint:** [Sprint 1 — L1→L2 Handoff Envelope](../../plans/260503-2317-l1-l2-handoff-envelope/README.md)

## Context

The 2026-05-03 audit identified the L1→L2 seam as the single highest-leverage failure point in the StoryForge pipeline. Four symptoms originate here:

1. **Silent-empty signals.** `pipeline/orchestrator_layers.py:400-421` reads L1 outputs with `getattr(draft, "...", None) or []`. L2 cannot distinguish "L1 didn't produce this" from "L1 produced it but extraction crashed." Both cases yield an empty list and L2 runs blind.
2. **Dual contract systems.** `ChapterContract` (L1) and `DramaContract` (L2) share zero fields and can directly contradict each other (`pacing_type=rising` vs `drama_target=0.4`). Each validates a disjoint slice of chapter requirements; nothing reconciles them.
3. **Voice profile schema drift.** Three legacy field names (`speech_quirks`, `dialogue_example`, `dialogue_samples`) are accepted via `or` fallback chains in `chapter_contract.py:312-319`. The fallbacks mask L1 emitting wrong-shaped voice data.
4. **Unattributable failures.** When a flat chapter ships, the operator cannot tell from `quality_scores` alone whether L1 conflict_web was empty, L2 simulator went advisory-only, or the contract gate misfired.

A typed envelope at one chokepoint, validated before the simulator runs, addresses all four.

## Decision

Introduce `L1Handoff` (Pydantic v2, `frozen=True`) as the single value passed from L1 to L2. Every signal field is paired with a `SignalHealth` entry (`ok | empty | malformed | extraction_failed`) so degradation is observable rather than silent. Persist the envelope as JSON on `pipeline_runs.handoff_envelope`.

Replace `ChapterContract` and `DramaContract` with one `NegotiatedChapterContract` per chapter: L1 fills its slice, the simulator fills the drama slice, the handoff gate reconciles and emits warnings.

## Tradeoffs

### Frozen Pydantic model

`model_config = ConfigDict(frozen=True)` makes `L1Handoff` immutable post-build. The envelope is a contract, not a scratchpad. Any L2 module that wants a mutated view must produce a new value (typically a `NegotiatedChapterContract`). This is intentionally restrictive — during P4 we will grep for `envelope.X.append(...)` patterns and refactor them. Cost: one upfront migration. Benefit: L2 can never silently mutate L1's contract.

### JSON persistence on `pipeline_runs` (no sidecar table)

Envelope is per-run, 1:1 cardinality. SQLite JSON1 supports `json_extract` for the diagnostics endpoint queries we need. A sidecar table would force a join on every read for zero schema benefit. YAGNI: revisit only if envelope size grows past ~1MB; current estimate is 5–50KB per run.

### `signals_version` field

Hardcoded `"1.0.0"` constant emitted on every envelope. We expect schema drift across sprints. The version field lets us write migration shims and surface "this envelope predates field X" cleanly in diagnostics, without runtime introspection of which fields are present.

### Single rubric vs dual contracts

`NegotiatedChapterContract` collapses `ChapterContract` + `DramaContract`. Risk: a check that one class enforced but the other did not could be lost. Mitigation: P5 (contract unification) includes a side-by-side rubric audit before the old classes are deleted; `code-reviewer` signs off on the mapping. Deletion of `DramaContract` happens in a separate commit from the migration so a single revert restores the old behaviour.

### Strict `extra="forbid"`

Every model in this module uses `extra="forbid"`. L1 cannot smuggle untyped fields through the envelope. If L1 starts producing a new signal, the schema must be extended deliberately. Cost: more friction adding fields. Benefit: schema drift cannot happen by accident.

## Consequences

**Easier:**
- Operators can answer "why is L2 advisory-only?" by reading `signal_health` from the diagnostics endpoint (P6).
- Adding a new L1 signal becomes a typed change in one file plus a builder update; consumers get a Pydantic error if they read a stale shape.
- Dropping `getattr(draft, "...", None) or []` patterns shrinks defensive code in L2 modules (audit cited 18 sites).
- One reconciliation point (`handoff_gate.reconcile_contract`) replaces ad-hoc clamps scattered across L1 and L2.

**Harder:**
- L2 modules must take an `L1Handoff` parameter explicitly instead of pulling fields off `draft`. Type signatures change in P4.
- Frozen envelope means any L2 code that mutated `draft.conflict_web` in place needs a refactor to local copies.
- New developers must learn the envelope as a layer of indirection. ADR + schema.md are the onboarding contract.
- `extra="forbid"` means voice profile schema cleanup (P2) must finish before envelope build, not after.

## References

- Plan: [`plans/260503-2317-l1-l2-handoff-envelope/README.md`](../../plans/260503-2317-l1-l2-handoff-envelope/README.md)
- Schema: [`plans/260503-2317-l1-l2-handoff-envelope/schema.md`](../../plans/260503-2317-l1-l2-handoff-envelope/schema.md)
- Phases: [`plans/260503-2317-l1-l2-handoff-envelope/phases.md`](../../plans/260503-2317-l1-l2-handoff-envelope/phases.md)
- Migration: [`plans/260503-2317-l1-l2-handoff-envelope/migration.md`](../../plans/260503-2317-l1-l2-handoff-envelope/migration.md)
- Risks: [`plans/260503-2317-l1-l2-handoff-envelope/risks.md`](../../plans/260503-2317-l1-l2-handoff-envelope/risks.md)
