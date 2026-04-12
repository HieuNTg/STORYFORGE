---
phase: 3
title: "Adaptive Simulation Intensity"
status: completed
effort: 2h
depends_on: [1, 2]
---

# Phase 3: Adaptive Simulation Intensity

## Context Links
- Plan: [plan.md](plan.md)
- Phase 1: [phase-01-psychology-engine.md](phase-01-psychology-engine.md)
- Phase 2: [phase-02-knowledge-causal.md](phase-02-knowledge-causal.md)
- Simulator: `pipeline/layer2_enhance/simulator.py` (run_simulation, lines 476-565)
- Drama patterns: `pipeline/layer2_enhance/drama_patterns.py` (tension curves)
- Config: `config.py` (pipeline config)

## Overview
Add a feedback loop to the simulation: if round N drama_score < threshold, round N+1 auto-escalates. Implement dynamic round count (stop when enough drama, extend when insufficient). Replace pure math tension curves with actual drama data.

## Key Insights
- `run_simulation()` uses fixed `num_rounds` (line 497) — always runs exactly N rounds regardless of drama quality
- `INTENSITY_CONFIG` (line 23) is static — selected once at start, never adapts
- `all_drama_scores` collected per round (line 524) but only used for final average — no feedback
- `get_tension_modifier()` in drama_patterns.py uses pure math (sine/linear) — not actual drama data
- Rounds with low drama waste LLM tokens; high-drama rounds could benefit from extension

## Requirements
1. Per-round drama score feedback: if score < threshold, escalate next round
2. Dynamic escalation: adjust temperature, escalation_scale, reaction_depth between rounds
3. Dynamic round count: min_rounds, max_rounds, stop condition (avg drama >= target)
4. Early stop when drama is sufficient (saves LLM tokens)
5. Extension when drama is insufficient (up to max_rounds)
6. Couple tension curve with actual drama scores, not just position math

## Architecture

### New file: `pipeline/layer2_enhance/adaptive_intensity.py` (~140 lines)

```python
DRAMA_THRESHOLD = 0.5          # Below this = weak round
DRAMA_TARGET = 0.65            # Stop when avg >= this
MIN_ROUNDS = 3
MAX_ROUNDS = 10

class RoundFeedback(BaseModel):
    round_number: int
    drama_score: float
    escalation_applied: bool = False
    note: str = ""

class AdaptiveController:
    def __init__(self, base_intensity: dict, min_rounds: int = 3, max_rounds: int = 10):
        self.base = dict(base_intensity)
        self.current = dict(base_intensity)
        self.min_rounds = min_rounds
        self.max_rounds = max_rounds
        self.history: list[RoundFeedback] = []

    def record_round(self, round_num: int, drama_score: float) -> None:
        """Record round result and adapt intensity for next round."""

    def should_continue(self, round_num: int) -> bool:
        """True if simulation should run another round."""

    def get_current_config(self) -> dict:
        """Return current intensity config (possibly escalated)."""

    def _escalate(self) -> None:
        """Bump temperature +0.05, escalation_scale +0.15, reaction_depth +1."""

    def _deescalate(self) -> None:
        """Slight cooldown after very high drama to prevent burnout."""

    def get_tension_modifier_actual(self, genre: str, round_num: int, total_rounds: int) -> float:
        """Blend math curve with actual drama history for tension modifier."""
```

### Escalation logic detail:
```python
def record_round(self, round_num, drama_score):
    fb = RoundFeedback(round_number=round_num, drama_score=drama_score)
    if drama_score < DRAMA_THRESHOLD:
        self._escalate()
        fb.escalation_applied = True
        fb.note = f"Weak round ({drama_score:.2f} < {DRAMA_THRESHOLD}), escalating"
    elif drama_score > 0.85:
        self._deescalate()
        fb.note = f"Very high drama ({drama_score:.2f}), slight cooldown"
    self.history.append(fb)

def should_continue(self, round_num):
    if round_num < self.min_rounds:
        return True
    if round_num >= self.max_rounds:
        return False
    avg = sum(h.drama_score for h in self.history) / len(self.history)
    return avg < DRAMA_TARGET

def _escalate(self):
    self.current["temperature"] = min(1.0, self.current["temperature"] + 0.05)
    self.current["escalation_scale"] = min(2.0, self.current["escalation_scale"] + 0.15)
    self.current["reaction_depth"] = min(4, self.current["reaction_depth"] + 1)

def _deescalate(self):
    self.current["temperature"] = max(0.7, self.current["temperature"] - 0.03)
    self.current["reaction_depth"] = max(1, self.current["reaction_depth"] - 1)
```

## Related Code Files
- `pipeline/layer2_enhance/simulator.py` — `run_simulation()` main loop, `_intensity` field
- `pipeline/layer2_enhance/drama_patterns.py` — `get_tension_modifier()`
- `pipeline/orchestrator_layers.py` — passes `num_sim_rounds` to simulator
- `config.py` — pipeline config for drama_intensity

## Implementation Steps

1. **Create `pipeline/layer2_enhance/adaptive_intensity.py`**:
   - `RoundFeedback` Pydantic model
   - `AdaptiveController.__init__(base_intensity, min_rounds=3, max_rounds=8)`
   - `record_round(round_num, drama_score)` — record + adapt
   - `should_continue(round_num)` — check min/max/avg logic
   - `get_current_config()` — return `self.current` dict
   - `_escalate()` — bump temperature +0.05, escalation_scale +0.15, reaction_depth +1 (with caps)
   - `_deescalate()` — reduce temperature -0.03, reaction_depth -1 (with floors)
   - `get_tension_modifier_actual(genre, round_num, total_rounds)` — blend `get_tension_modifier()` math result with actual drama average: `0.6 * math_modifier + 0.4 * (1.0 - avg_drama)`

2. **Modify `simulator.py` `run_simulation()`** (line 476):
   - Import `AdaptiveController`
   - After line 492 (`self._intensity = _get_intensity_config(drama_intensity)`): create `self.adaptive = AdaptiveController(self._intensity, min_rounds=max(3, num_rounds-2), max_rounds=num_rounds+3)`
   - Replace `for round_num in range(1, num_rounds + 1)` (line 497) with:
     ```python
     round_num = 0
     while True:
         round_num += 1
         if round_num > 1 and not self.adaptive.should_continue(round_num):
             _log(f"Drama sufficient after {round_num-1} rounds, stopping early")
             break
         self._intensity = self.adaptive.get_current_config()
     ```
   - After `all_drama_scores.append(...)` (line 524): call `self.adaptive.record_round(round_num, evaluation.get("overall_drama_score", 0.5))`
   - In `_check_escalation()` (line 399): replace `get_tension_modifier(genre, position)` with `self.adaptive.get_tension_modifier_actual(genre, round_num, total_rounds)` — wrap in try-except, fallback to original

3. **Add `adaptive_rounds` metadata to `SimulationResult`**:
   - Add field: `actual_rounds: int = Field(default=0, description="Actual rounds run (may differ from requested)")`
   - Set it in `run_simulation()` result building

4. **Update `orchestrator_layers.py`** (no changes needed — `num_rounds` becomes the base, adaptive controller handles actual count)

## Todo
- [ ] Create adaptive_intensity.py with AdaptiveController
- [ ] Add actual_rounds field to SimulationResult schema
- [ ] Replace fixed loop in run_simulation with adaptive while loop
- [ ] Wire record_round after drama evaluation
- [ ] Wire get_current_config into each round's intensity
- [ ] Wire get_tension_modifier_actual into _check_escalation
- [ ] Log adaptive decisions for debugging

## Success Criteria
- Low-drama simulations automatically escalate intensity in subsequent rounds
- High-drama simulations stop early (saving 1-3 LLM round trips)
- `actual_rounds` in SimulationResult reflects real count
- Tension modifier blends math curve with actual drama data
- Pipeline runs normally when adaptive_intensity import fails

## Risk Assessment
- **Infinite loop**: Mitigated by `max_rounds` hard cap in `should_continue()`
- **Over-escalation**: Mitigated by caps on temperature (1.0), escalation_scale (2.0), reaction_depth (4)
- **Under-escalation**: If threshold too high, may never stop. Mitigated: target 0.65 is reasonable median.

## Security Considerations
- No new external dependencies
- No user-facing config changes (adaptive is internal optimization)

## Next Steps
Phase 4 uses the enriched simulation output (psychology, knowledge, causal chains, adaptive drama scores) to enhance at scene level with dialogue subtext and thematic tracking.
