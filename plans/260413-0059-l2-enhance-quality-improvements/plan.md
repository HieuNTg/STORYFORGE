---
title: "L2 Enhancement Quality — Signal Integration, Causal Accountability, Contract Gate"
description: "Wire L1 Phase 1-5 signals into L2 + add causal/psychology/contract enforcement"
status: in-progress
priority: P1
effort: 19-20h
branch: master
tags: [layer2, enhancement, signal-integration, causal, contract, quality]
created: 2026-04-13
progress: 3/5 phases complete
---

# L2 Enhancement Quality Improvements

L2 (`pipeline/layer2_enhance/`) is architecturally orphaned from L1 Phase 1-5 signals — audit found 0 references to `arc_waypoints`, `pacing_adjustment`, `structured_summary`, `ChapterContract`, `PlotThread.urgency`. L1 emits them; L2 ignores them. Plan wires signals in, adds causal accountability + contract gate.

## Phases

| # | Phase | Effort | Status | File |
|---|---|---|---|---|
| A | L1 Signal Integration (conflict_intensity emission, waypoints, summary, pacing, thread status, Chapter.contract wiring) | 7-9h | DONE (2026-04-13) | [phase-A-signal-integration.md](./phase-A-signal-integration.md) |
| D | Cleanup (dead code, dup structs) | 1-2h | DONE (2026-04-13, scoped) | [phase-D-cleanup.md](./phase-D-cleanup.md) |
| B | Causal Accountability (revelation DAG, knowledge log, text auditor) | 4-6h | DONE (2026-04-13) | [phase-B-causal-accountability.md](./phase-B-causal-accountability.md) |
| C | Thread-Urgency → Psychology Pressure | 2-3h | **NEXT** | [phase-C-thread-urgency-psychology.md](./phase-C-thread-urgency-psychology.md) |
| E | Contract Gate (pre/post validation + optional rewrite) | 3-4h | pending | [phase-E-contract-gate.md](./phase-E-contract-gate.md) |

## Progress

**3 of 5 phases complete** (Phase A, Phase D, Phase B — 2026-04-13). **Next: Phase C (Thread-Urgency → Psychology Pressure).**

### Phase A Completion Summary
- **Implementation**: 8 files modified — `pipeline/layer2_enhance/{_agent,simulator,scene_enhancer,adaptive_intensity,enhancer}.py`, `pipeline/orchestrator_layers.py`, `pipeline/layer1_story/batch_generator.py`, `models/schemas.py`, `config/defaults.py`
- **Tests**: `tests/test_l2_signal_integration.py` — 16 new tests, all passing
- **Review**: 7.5/10, 3 critical issues auto-fixed, approved
- **Completed**: 2026-04-13

### Phase D Completion Summary (scoped)
- **Scoped execution**: 1 of 7 original deletion targets was provably dead — `extract_conflict_graph` + `_calc_tension` in `analyzer.py` (37 LOC removed)
- **Blob fallback** (`enhancer.py:156`) marked `DEPRECATED` with removal scheduled next sprint
- **5 items SKIPPED** with grep-verified rationale (preserving test coverage, actively-used aliases, and emitted event types — details in `phase-D-cleanup.md`)
- **Tests**: 170/170 pass (no regressions)
- **Review**: 9/10, 0 critical
- **Completed**: 2026-04-13

### Phase B Completion Summary
- **Implementation**: 8 files — `pipeline/layer2_enhance/{causal_chain,knowledge_system,simulator,enhancer}.py`, `pipeline/orchestrator_layers.py`, `services/prompts/layer2_enhanced_prompts.py`, `services/prompts/__init__.py`, `tests/test_causal_audit.py`
- **Tests**: 18/18 pass (`tests/test_causal_audit.py`)
- **Review**: 9/10 after 1 auto-fix cycle (from initial 6/10); approved
- **Notable fixes**: removed unused `prerequisite_event_ids` (YAGNI), `register_secret` now seeds `reveal_log` for initial holder, audit capped at 40 chapters for cost bound
- **Completed**: 2026-04-13

## Dependency Diagram

```
A (expose signals) ─┬─► D (remove now-redundant code)
                    ├─► B (uses arc_waypoints + thread.status + structured_summary)
                    │   └─► C (uses thread.urgency from A + psychology_engine)
                    │       └─► E (gates final output using B+C state vs ChapterContract)
                    └─► (C can start after A without strict B dep)
```

Execution: **A → D → B → C → E**. D runs after A because A exposes L1 signals that some dead code was loosely replacing. B/C before E because E validates outputs of B (causality-clean) and C (psychology-informed).

## LLM Cost Impact

| Phase | New calls | Savings | Net |
|---|---|---|---|
| A | 0 | -20–30% on scene_enhancer re-analysis (A.2 feeds `structured_summary` → skip LLM extract) | Saves ~1 LLM call per weak scene |
| D | 0 | +0 runtime (dead code removal) | Zero |
| B | +1 per chapter (text auditor, cheap tier) | 0 | +N calls (N=chapter count), cheap-tier |
| C | 0 (pure Python pressure bumps) | 0 | Zero |
| E | 0–1 per chapter (only rewrite on ≥2 critical failures) | 0 | +~0.3×N in practice |

Estimated: ~15% LLM volume increase worst case, ~10% decrease if A.2 lands cleanly. Config flag `L2_CONTRACT_GATE_ENABLED=true` lets us A/B test.

## Rollback Plan

- All new behavior behind feature flags in `config.py` (or env): `L2_USE_L1_SIGNALS`, `L2_CAUSAL_AUDIT`, `L2_THREAD_PRESSURE`, `L2_CONTRACT_GATE`. Default `true` for A/C, `true` with single-retry cap for B/E.
- Each phase ships its own commit; git revert per phase if regression.
- `structured_summary` / `arc_waypoints` reads use `getattr(x, "field", default)` pattern — no crash on older drafts.
- Contract gate has hard cap `max_retries=1` + timeout; on failure, keep original enhanced chapter and log warning (non-fatal).

## Acceptance (full plan)

- All 5 phase `Success Criteria` met.
- `pytest tests/` green, including new `tests/test_l2_signal_integration.py`, `tests/test_causal_audit.py`, `tests/test_contract_gate.py`.
- Run on `examples/` fixture story → enhanced output shows waypoints respected, no causality violations flagged, contract pass rate ≥ 85%.
- LLM call budget within +15%/-10% range logged by `services/llm/retry.py` counter.

## Validation Summary

**Validated:** 2026-04-13
**Questions asked:** 4

### Confirmed Decisions
- **`conflict_intensity` signal** → Add L1 emission as new sub-step **Phase A.0** (+1h). Extend `conflict_web_builder` to emit intensity 1–5 per conflict.
- **`Chapter.contract` field** → Add in **Phase A** (bundled with A.1–A.4 signal reads), not deferred to Phase E. Earlier integration surfacing.
- **Blob fallback** (`enhancer.py:94–187`) → Phase D marks `@deprecated` + log warning only. Delete next sprint.
- **Phase E rewrite threshold** → Keep plan default: `≥2 critical OR ≥1 critical + ≥2 warnings`.

### Action Items
- [ ] Phase A file: prepend **A.0 — L1 conflict intensity emission** (modifies L1 `conflict_web_builder.py`, +1h). Update phase effort to 7–9h.
- [ ] Phase A file: add **A.5 — Chapter.contract schema wiring** (moved from Phase E.0). Update total effort to match.
- [ ] Phase D file: reframe blob fallback from "delete" to "deprecate" — add `warnings.warn(DeprecationWarning)` + docstring note.
- [ ] Phase E file: remove E.0 schema step (now done in A); clarify threshold rationale.
- [ ] `plan.md` effort total: 18h → **19–20h** after A.0 addition.

### Recommendation
Proceed to implementation via `/code:auto`. No blocking questions remain.
