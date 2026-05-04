# StoryForge Sprint Plans

Each directory holds the planning artefacts for one sprint: `README.md` (goal, success criteria, decisions), `phases.md`, `schema.md`, `migration.md`, `risks.md`. Single sprint branch, one PR to `master` per the project git policy.

## Index

| Sprint | Dir | Status | Outcome |
|--------|-----|--------|---------|
| 1 | [`260503-2317-l1-l2-handoff-envelope/`](./260503-2317-l1-l2-handoff-envelope/README.md) | DONE | Typed `L1Handoff` envelope + `NegotiatedChapterContract`; reconciliation gate at `pipeline/handoff_gate.py`; `STORYFORGE_HANDOFF_STRICT` env flag; envelope persisted on `pipeline_runs`. |
| 2 | [`260504-1213-semantic-verification/`](./260504-1213-semantic-verification/README.md) | DONE | Embedding-based foreshadowing payoff verifier (threshold retuned to 0.55, 96.67% acc on Vietnamese 30-pair set); spaCy NER for character presence; objective outline metrics; `STORYFORGE_SEMANTIC_STRICT` env flag; diagnostics endpoint + UI panel. |
| 3 | [`260504-1356-generation-hardening/`](./260504-1356-generation-hardening/README.md) | DONE | `NegotiatedChapterContract.drama_ceiling` wired into chapter writer (Vietnamese `## RÀNG BUỘC KỊCH TÍNH` directive); speaker-anchored voice revert; async D3 contract; batched structural rewriter; Sprint 2 carry-over cleanup. |

## Reports

Per-task reports from agent executions land in [`reports/`](./reports/) using the convention `<Agent>-<YYMMDD>-<HHMM>-<slug>.md`.

## ADRs

Sprint outcomes are summarised as ADRs in [`docs/adr/`](../docs/adr/).
