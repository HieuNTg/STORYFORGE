# Phase C — Thread-Urgency → Psychology Pressure

## Context Links
- Parent plan: [plan.md](./plan.md)
- Research: [researcher-02-causal-contract.md](./research/researcher-02-causal-contract.md) §4, §6
- Depends on: Phase A (PlotThread.status + urgency read-path)

## Overview
- **Date**: 2026-04-13
- **Description**: Convert `PlotThread.urgency` (1-5) into `CharacterPsychology.pressure` bumps when a character is involved in a stale, urgent thread. Wires the urgency signal into simulator round generation so characters behave under appropriate tension.
- **Priority**: P2 (drama tuning, moderate uplift)
- **Effort**: 2-3h
- **Implementation Status**: DONE
- **Review Status**: approved (8/10, 1 fix cycle)

## Key Insights
- `PsychologyEngine.update_pressure` (`psychology_engine.py:107`) already handles `event_type` + `attacker` bumps — natural extension point for thread-driven pressure.
- `PlotThread.urgency` (`models/schemas.py:129`) is `int` [1,5]. `thread.last_mentioned_chapter` gives staleness. Together = implicit deadline.
- `CharacterPsychology.pressure` bounded [0,1] (`schemas.py:258`). Headroom: typical baseline ~0.2–0.4 after a few events.
- Pure-Python, no LLM. DRY win — no re-scoring.
- Inflation risk: 5 stale threads → +1.0 pressure saturation. Cap per-chapter thread contribution at +0.3.

## Requirements
- R-C1: New method `PsychologyEngine.apply_thread_pressure(psychology, threads, current_chapter) → None`.
- R-C2: Pressure rule: for each `thread` where `character ∈ thread.involved_characters`:
  - `urgency >= 4` AND `current_chapter - thread.last_mentioned_chapter >= 2` → `+0.15`
  - `urgency == 5` AND `status == "open"` → additional `+0.05`
  - `urgency <= 2` → no bump
- R-C3: Cap per-chapter cumulative thread contribution at `+0.30`.
- R-C4: Call site: pre-simulator in `DramaSimulator.setup_agents` or pre-round in `simulator.py` round loop. Prefer per-chapter hook in enhancer → simulator (once per chapter).
- R-C5: Feature flag `L2_THREAD_PRESSURE` (default `true`).
- R-C6: Logging: `logger.info(f"[Pressure] {char}: +{delta:.2f} from {len(stale_threads)} stale urgent threads")`.
- R-C7: Backward-compat: no crash if `threads` empty or `PlotThread.urgency` missing.

## Architecture

```
enhancer (per chapter)
    │
    ├── collect PlotThread list (draft.open_threads + resolved_threads)
    ├── for each character with psychology:
    │     psychology_engine.apply_thread_pressure(
    │         char.psychology, threads, chapter.chapter_number
    │     ) → modifies pressure in-place
    │
    └── simulator reads updated pressure → higher temperature / more desperate posts

Pressure contributors (existing + new):
  baseline (0)
  + wound_keywords (update_pressure) [existing]
  + exploiter_present (update_pressure) [existing]
  + thread_urgency (apply_thread_pressure) [NEW, cap +0.30/chapter]
```

## Related code files
- `pipeline/layer2_enhance/psychology_engine.py:107` — `update_pressure` (reference for new method style)
- `pipeline/layer2_enhance/psychology_engine.py` (new method) — `apply_thread_pressure`
- `pipeline/layer2_enhance/simulator.py:125` or `enhancer.py:85` — call site
- `models/schemas.py:118–129` — `PlotThread` (read-only)
- `models/schemas.py:255–260` — `CharacterPsychology` (read/write pressure)
- `config.py` — `L2_THREAD_PRESSURE` flag
- `tests/test_thread_pressure.py` — new tests

## Implementation Steps

1. **C.1 New method in `psychology_engine.py`**:
   ```python
   def apply_thread_pressure(
       self,
       psychology: CharacterPsychology,
       threads: list[PlotThread],
       current_chapter: int,
       max_bump: float = 0.30,
   ) -> None:
       """Bump pressure for characters in stale urgent threads."""
       total = 0.0
       matched = []
       for t in threads:
           if psychology.character_name not in t.involved_characters:
               continue
           urgency = getattr(t, "urgency", 3)
           if urgency < 4:
               continue
           staleness = current_chapter - getattr(t, "last_mentioned_chapter", current_chapter)
           if staleness < 2:
               continue
           bump = 0.15 + (0.05 if urgency == 5 and t.status == "open" else 0.0)
           total = min(max_bump, total + bump)
           matched.append(t.thread_id)
       if total > 0:
           psychology.pressure = min(1.0, psychology.pressure + total)
           logger.info(
               f"[Pressure] {psychology.character_name}: +{total:.2f} from {len(matched)} urgent stale threads"
           )
   ```
   - Confirm `CharacterPsychology.character_name` exists (`schemas.py:~255`); if not, pass char name as arg.
2. **C.2 Call site** — in `enhancer.py` around `:85` (chapter loop) OR in `simulator.py:125` `setup_agents` — prefer enhancer to keep per-chapter knowledge current:
   ```python
   if config.L2_THREAD_PRESSURE:
       all_threads = list(getattr(draft, "open_threads", [])) + list(getattr(draft, "resolved_threads", []))
       for char in draft.characters:
           psych = getattr(char, "psychology", None)
           if psych:
               engine.apply_thread_pressure(psych, all_threads, chapter.chapter_number)
   ```
3. **C.3 Config flag** — add `L2_THREAD_PRESSURE: bool = True` to `config.py`.
4. **C.4 Feed into simulator** — no code change needed; simulator already reads `CharacterPsychology.pressure` via `PsychologyEngine.compute_drama_potential` (`psychology_engine.py:94`). Increased pressure → higher drama_multiplier → more intense posts.
5. **Tests** `tests/test_thread_pressure.py`:
   - Urgent stale thread → pressure bumps +0.15.
   - Urgency 5 open thread → +0.20.
   - Character not involved → no bump.
   - Staleness < 2 → no bump.
   - 5 matching threads → capped at +0.30 (not +0.75).
   - flag off → pressure unchanged.
   - Empty `threads` list → no crash.

## Todo
- [x] C.1 Implement `apply_thread_pressure` in `psychology_engine.py`
- [x] C.2 Wire call site in `enhancer.py` (per-chapter loop)
- [x] C.3 `L2_THREAD_PRESSURE` flag in `config.py`
- [x] Write `tests/test_thread_pressure.py` (7 cases)
- [x] Run pytest — green
- [x] Log-based sanity check on fixture story: pressure distribution shifts as expected

## Completion Notes
- 12/12 tests pass; review 8/10 after 1 fix cycle
- Fixed `last_mentioned_chapter=0` fallback to use `planted_chapter` (sibling-module convention)
- **Files changed**: `pipeline/layer2_enhance/psychology_engine.py`, `pipeline/layer2_enhance/simulator.py`, `tests/test_thread_pressure.py`
- **Scope decisions**: wired call site in `simulator.setup_agents` (not per-chapter enhancer) — pressure is set once at sim init and evolves via `update_pressure` during rounds; simpler and matches existing psychology lifecycle

## Success Criteria
- Characters in urgent stale threads show pressure bumps in logs.
- Cap enforced: no character receives >+0.30 per chapter from threads.
- `simulator` output posts for high-pressure characters have measurably higher `drama_score` (validated on fixture, not asserted in tests — too fuzzy).
- Zero regressions in existing `test_psychology_engine.py` (if exists; create minimal if not).

## Risk Assessment
- **Pressure saturation**: if every urgent thread involves protagonist, pressure hits 1.0 fast. Cap mitigates but protagonist may stay capped all book. Mitigate: decay at chapter boundaries (subtract 0.05 before bumping), or per-chapter window of bumps.
- **Frozen urgency**: if L1 sets `thread.urgency` at plant time and never updates, all urgencies stay static — Phase C pressure doesn't decay with narrative resolution. Mitigate: also reduce pressure when thread transitions `open → resolved` (negative bump -0.10). Defer to follow-up if L1 emission is frozen.
- **Character name mismatch**: `PlotThread.involved_characters` uses display names; `CharacterPsychology` may key on canonical names. Mitigate: normalize (lowercase, strip whitespace) before compare.
- **Double-counting**: if both `update_pressure` (from an event involving same character) AND `apply_thread_pressure` fire in same chapter, total can exceed cap. Acceptable; per-source caps not global.

## Security Considerations
- No external input, no LLM calls, pure in-memory math.
- No new data writes.

## Next Steps
- Phase E validates contract at chapter level — pressure-driven simulator output fed into Phase E's pacing/arc validation.

## Unresolved Questions
1. Does `PlotThread.urgency` update across chapters, or frozen at plant time (researcher-02 §9 Q5)? Determines whether decay rule needed.
2. `CharacterPsychology.character_name` — exact field name? If absent, pass char name explicitly to `apply_thread_pressure`.
3. Should resolving a thread reduce pressure for involved characters (negative bump)? Symmetric but doubles state management.
4. Per-chapter cap `+0.30` — arbitrary. Consider tuning after 3 fixture runs.
5. Call site: enhancer (per-chapter, simple) vs. simulator.setup_agents (once, cleaner but coarser)? Current plan: enhancer.
