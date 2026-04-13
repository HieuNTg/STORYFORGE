# Phase B — Causal Accountability

## Context Links
- Parent plan: [plan.md](./plan.md)
- Research: [researcher-02-causal-contract.md](./research/researcher-02-causal-contract.md) §1, §2, §3, §7
- Depends on: Phase A (thread.status + structured_summary) and Phase D (clean CausalGraph surface)

## Overview
- **Date**: 2026-04-13
- **Description**: Close the causality loophole — enforce that simulator/text events respect prior events. Extend `CausalGraph` to explicitly tag prerequisites, fix `KnowledgeRegistry` scalar-`revealed_round` bug, add post-L2 text auditor that verifies "X learns from Z" isn't contradicted by an earlier "Y told X".
- **Priority**: P1 (biggest plot coherence uplift)
- **Effort**: 4-6h
- **Implementation Status**: DONE (2026-04-13)
- **Review Status**: approved (9/10, after 1 auto-fix cycle from 6/10)

## Key Insights
- `CausalEvent.cause_event_id` is **single-parent** (`causal_chain.py:11`). Many revelation events have multiple prerequisites (e.g., "Y confronts X" needs both "Y discovered the letter" AND "X is present"). Need `prerequisite_event_ids: list[str]` alongside single `cause_event_id`.
- `KnowledgeItem.revealed_round: int` (`knowledge_system.py:14`) is **scalar** — overwritten on each `reveal_to`. Can't reconstruct "who learned when". Promote to `reveal_log: list[dict]` keyed by character.
- `_infer_cause` requires ≥2-char overlap (`causal_chain.py:68`) — lone-discovery revelations will never link. Lower threshold for revelation events specifically.
- `check_revelation_triggers` (`knowledge_system.py:130`) emits dicts but **never** creates `CausalEvent` entries — revelations happen invisibly to the graph.
- Post-L2 text auditor = new LLM call per chapter (cheap tier). Single bundled call asking "scan this chapter for `[character] discovered/found out [fact]` — return `{fact, claimed_source, alternative_source}` if ambiguous". Then cross-ref registry.

## Requirements
- R-B1: `CausalEvent` gains `prerequisite_event_ids: list[str] = []` — multi-parent support. `cause_event_id` kept as primary for back-compat.
- R-B2: `KnowledgeItem.revealed_round` → `reveal_log: list[RevealEntry]` where `RevealEntry = {char: str, round: int, source: str}`. Back-compat shim: property `revealed_round` returns max round in log.
- R-B3: `knowledge_system.reveal_to` MUST emit a `CausalEvent` (type=`"tiết_lộ"`) and link its `cause_event_id` to the most-recent prior reveal of the same `fact_id`.
- R-B4: New `causal_chain.record_revelation_event(graph, registry, fact_id, revealer, receiver, round_num) → event_id` per researcher spec §7.
- R-B5: New `causal_chain.audit_revelation_causality(graph, registry, enhanced_chapters) → list[dict]` — returns per-chapter flags for text claiming a revelation source that contradicts the registry.
- R-B6: Bundled LLM auditor: ONE prompt per chapter extracting `{fact_mentions, claimed_sources}`; cross-check in pure Python — no N+1 calls.
- R-B7: Post-L2 wiring: call auditor after `coherence_validator.fix_coherence_issues` (`enhancer.py:330ish`). On high-confidence violation, append to `chapter.enhancement_changelog` + optionally flag for rewrite (defer rewrite to Phase E).
- R-B8: Feature flag `L2_CAUSAL_AUDIT` (default `true`).
- R-B9: Witness heuristic: treat all characters in the same `AgentPost` round window (±1 round) as witnesses — they gain knowledge too. Prevents false-positive auditor flags.

## Architecture

```
Simulator round N
    │
    ├── CharacterAgent posts → check_revelation_triggers (knowledge_system.py:130)
    │       │
    │       └── for each triggered reveal:
    │             reveal_to(fact_id, char, N) ─┐
    │             witnesses in ±1 round also  │
    │             gain knowledge ─────────────┤
    │                                         │
    │             record_revelation_event ────┘ (B.4)
    │                   │
    │                   ├── create CausalEvent(type=tiết_lộ)
    │                   ├── cause_event_id = last reveal of this fact_id
    │                   └── prerequisite_event_ids = [events that put
    │                       revealer in position to know]
    │
    └── [after all rounds] → graph + registry frozen

Enhancer post-L2 (B.5 audit)
    │
    ├── [per enhanced chapter]
    │     ├── LLM extract: {fact_mentions: [{fact, claimed_source, sentence}]}
    │     ├── cross-ref registry.reveal_log:
    │     │     - fact's known_by includes claimed_source? ✔
    │     │     - claimed_source's revealed_round < this chapter's round? ✔
    │     │     - no prior revealer mentioned in text for same fact?
    │     └── collect violations → chapter.enhancement_changelog
    │
    └── if violations ≥ 2 critical → tag for Phase E rewrite
```

## Related code files
- `pipeline/layer2_enhance/causal_chain.py:9–18` — extend `CausalEvent` model
- `pipeline/layer2_enhance/causal_chain.py:28–62` — `add_event` (populate prerequisites)
- `pipeline/layer2_enhance/causal_chain.py:64–79` — `_infer_cause` (lower threshold for revelation type)
- `pipeline/layer2_enhance/causal_chain.py` (new) — `record_revelation_event`, `audit_revelation_causality`
- `pipeline/layer2_enhance/knowledge_system.py:9–16` — `KnowledgeItem` (reveal_log)
- `pipeline/layer2_enhance/knowledge_system.py:63–80` — `reveal_to` (log + emit CausalEvent)
- `pipeline/layer2_enhance/knowledge_system.py:130–150` — `check_revelation_triggers` (witness propagation)
- `pipeline/layer2_enhance/enhancer.py` (post-`fix_coherence_issues`) — wire auditor
- `services/prompts.py` — new `CAUSAL_AUDIT_EXTRACT` Vietnamese prompt
- `config.py` — `L2_CAUSAL_AUDIT` flag
- `tests/test_causal_audit.py` — new tests

## Implementation Steps

1. **B.1 Schema extensions**:
   - `causal_chain.py:9` `CausalEvent` add `prerequisite_event_ids: list[str] = Field(default_factory=list)`.
   - `knowledge_system.py` add `class RevealEntry(BaseModel): char: str; round: int; source: str = ""`.
   - `knowledge_system.py:9–16` `KnowledgeItem` replace `revealed_round: int = 0` with `reveal_log: list[RevealEntry] = Field(default_factory=list)` + compat `@property revealed_round`.
2. **B.2 Update reveal_to**:
   - `knowledge_system.py:63` `reveal_to(fact_id, char_name, round_num, source: str = "")`.
   - Append `RevealEntry(char=char_name, round=round_num, source=source)` to `fact.reveal_log`; append to `known_by` if not already.
   - Return `RevealEntry` for caller.
3. **B.3 `record_revelation_event`** (new in `causal_chain.py`):
   - Signature: `record_revelation_event(graph: CausalGraph, registry: KnowledgeRegistry, fact_id: str, revealer: str, receiver: str, round_num: int) → str`.
   - Find prior reveal of `fact_id` → use its CausalEvent id as `cause_event_id` (if any).
   - Create `CausalEvent(event_type="tiết_lộ", characters_involved=[revealer, receiver], description=f"{revealer} tiết lộ '{fact_id}' cho {receiver}")`.
   - Call `graph.add_event(synthetic_event, cause_id=prior_reveal_id)`.
   - Return new event_id.
4. **B.4 Adjust `_infer_cause`** for revelation events:
   - `causal_chain.py:64` — if `event.event_type == "tiết_lộ"`, allow 1-char overlap (lone discovery) and look back up to 2 rounds instead of 1.
5. **B.5 Witness propagation** in `check_revelation_triggers`:
   - `knowledge_system.py:130` — build `witnesses: set[str]` = chars present in posts of round `round_num-1..round_num+1`.
   - For each fact revealed to `post.target`, also add `witnesses - {post.target}` to `known_by` with `source="witness"`.
   - Cap witnesses at 3 per revelation to avoid spam.
6. **B.6 LLM auditor**:
   - New prompt `CAUSAL_AUDIT_EXTRACT` in Vietnamese — returns JSON `{"fact_mentions": [{"fact":"...", "claimed_source":"...", "sentence":"..."}]}`.
   - Call at enhancer after `fix_coherence_issues`. Cheap tier, max_tokens 500. One call per chapter.
   - Python cross-ref: for each mention, look up by fuzzy-match fact→`KnowledgeItem` (simple substring / token overlap); if no match → skip. If match found, compare `claimed_source` vs. `reveal_log[0].char` (earliest revealer). If mismatch AND `claimed_source ∉ known_by`, flag.
7. **B.7 Wire into enhancer**:
   - `enhancer.py` — after `fix_coherence_issues`, if `L2_CAUSAL_AUDIT`:
     ```python
     violations = audit_revelation_causality(graph, registry, enhanced.chapters)
     for v in violations:
         chapter.enhancement_changelog.append(f"[causality] {v['msg']}")
     enhanced._causality_flags = violations  # for Phase E
     ```
8. **B.8 Config flag** — add `L2_CAUSAL_AUDIT: bool = True` to `config.py`.
9. **Tests** `tests/test_causal_audit.py`:
   - Two sequential reveals → second has correct `cause_event_id`.
   - Text says "X learned from Y" but registry says Z was earlier revealer + `X ∉ witnesses` → flagged.
   - Witness propagation: char in ±1 round range gains knowledge.
   - `reveal_log` preserves order after 3 sequential reveals.
   - `revealed_round` compat property returns max round.
   - flag off → auditor skipped.

## Todo
- [~] B.1 `CausalEvent.prerequisite_event_ids` — SKIPPED (YAGNI, removed during review auto-fix; `_infer_cause` only finds 1 parent so field was unused)
- [x] B.1 `KnowledgeItem.reveal_log` (replace scalar) + `@property revealed_round`
- [x] B.2 `reveal_to` append to log + return entry
- [x] B.3 `record_revelation_event` new fn
- [x] B.4 `_infer_cause` relaxed threshold for revelation type
- [x] B.5 Witness propagation in `check_revelation_triggers`
- [x] B.6 Add `CAUSAL_AUDIT_EXTRACT` Vietnamese prompt
- [x] B.6 Implement `audit_revelation_causality` (LLM + Python cross-ref)
- [x] B.7 Wire into `enhancer.py` post-coherence
- [x] B.8 `L2_CAUSAL_AUDIT` flag in `config.py`
- [x] Write `tests/test_causal_audit.py` (6+ cases → 18 total)
- [x] Run pytest — green (18/18)

## Success Criteria
- Revelation events visible in `graph.events` with `event_type="tiết_lộ"` and non-empty `cause_event_id` when prior reveal exists.
- Auditor on seeded violation (hand-crafted chapter text claiming wrong source) → flags it in `enhancement_changelog`.
- Witness heuristic eliminates ≥80% of false-positive flags on test stories (measured on 3 fixture stories).
- `reveal_log` contains all reveals in order; `.revealed_round` property unchanged behavior.
- Max +1 LLM call per chapter from auditor, cheap tier.

## Risk Assessment
- **False-positive flags**: fuzzy fact-matching by substring is noisy. Mitigate: require ≥70% token overlap AND exact character name match before flagging; lower severity on partial matches.
- **Witness over-broadcast**: characters in 3 rounds around a reveal all gain knowledge — breaks dramatic-irony beats ("only A knows"). Mitigate: skip witness propagation when `fact.dramatic_irony=True`.
- **Multi-parent semantics**: populating `prerequisite_event_ids` is speculative — `_infer_cause` only finds 1 parent. Mitigate: leave empty by default; populate only when `check_revelation_triggers` has explicit evidence (e.g., both a post and a prior reveal).
- **Schema migration**: `revealed_round: int` → `reveal_log: list` is a breaking change. Mitigate: property shim returns `max(entry.round for entry in reveal_log) if reveal_log else 0`. Run schema-write migration for any persisted state.
- **LLM auditor hallucination**: might fabricate revelations not in text. Mitigate: require the returned `sentence` be a substring of chapter.content before trusting the flag.

## Security Considerations
- New LLM call sends chapter text + fact list; same data already sent by enhancer — no new data exposure.
- No user input; all internal.

## Next Steps
- Phase C consumes `KnowledgeRegistry.reveal_log` to influence pressure (e.g., "char just learned secret → spike pressure").
- Phase E rewrite-gate uses `_causality_flags` to decide if chapter needs rewrite.

## Unresolved Questions
1. Should `prerequisite_event_ids` be auto-populated, or left for manual use? Auto-population risks wrong inference; manual = unused field.
2. Witness propagation: include characters who didn't post in the window but were in `character_locations` for same scene? Requires scene-presence data we don't have.
3. What severity levels for auditor flags? Binary (critical/non-critical), or 3-tier (error/warning/info)?
4. Fact-matching threshold — 70% token overlap is arbitrary. Consider embedding similarity (adds dep) vs. keyword lists per `fact_id`.
5. Should auditor run only on enhanced chapters, or also on the L1 draft? Doubles LLM cost; probably defer.

## Completion Notes

**Completed**: 2026-04-13
**Review**: 9/10 (after 1 auto-fix cycle from initial 6/10) — approved
**Tests**: 18/18 pass (`tests/test_causal_audit.py`)

### Files changed
- `pipeline/layer2_enhance/causal_chain.py`
- `pipeline/layer2_enhance/knowledge_system.py`
- `pipeline/layer2_enhance/simulator.py`
- `pipeline/layer2_enhance/enhancer.py`
- `pipeline/orchestrator_layers.py`
- `services/prompts/layer2_enhanced_prompts.py`
- `services/prompts/__init__.py`
- `tests/test_causal_audit.py`

### Notable fixes from review (6/10 → 9/10 auto-fix cycle)
- **Removed unused `prerequisite_event_ids`** — YAGNI: `_infer_cause` only finds a single parent, field was never populated. Dropped from `CausalEvent` schema.
- **`register_secret` now seeds `reveal_log`** for the initial holder, so the earliest known_by entry is traceable (prior version left `reveal_log` empty until first `reveal_to`).
- **Audit capped at 40 chapters** — bounds worst-case LLM cost for long stories; chapters beyond cap skip the auditor call (still logged).

### Skipped items
- **B.1 `prerequisite_event_ids`** — intentionally removed during review as YAGNI (see above). If multi-parent inference lands later (e.g., from an LLM-backed `_infer_cause`), reintroduce then.
- **Config-file flag** — `L2_CAUSAL_AUDIT` wired via `config/defaults.py`-style access rather than a new `config.py` constant (consistent with Phase A pattern).
