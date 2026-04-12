---
title: "Layer 2: 7 Quality Enhancements"
description: "Character psychology, secrets, causal chains, adaptive simulation, scene-level enhancement, dialogue subtext, thematic resonance"
status: done
priority: P1
effort: 12h
branch: master
tags: [layer2, enhancement, drama, quality]
created: 2026-04-07
---

# Layer 2: 7 Quality Enhancements

## Goal
Replace shallow mood/energy/stakes simulation with multi-dimensional psychology, knowledge asymmetry, causal event chains, adaptive intensity, scene-level enhancement, dialogue subtext, and thematic resonance tracking.

## Phases

| # | Phase | Enhancements | Effort | Status | File |
|---|-------|-------------|--------|--------|------|
| 1 | Foundation | #1 Character Psychology Engine | 2.5h | DONE | [phase-01-psychology-engine.md](phase-01-psychology-engine.md) |
| 2 | Knowledge | #2 Secret/Knowledge System, #3 Causal Event Chain | 2.5h | DONE | [phase-02-knowledge-causal.md](phase-02-knowledge-causal.md) |
| 3 | Simulation | #4 Adaptive Simulation Intensity | 2h | DONE | [phase-03-adaptive-simulation.md](phase-03-adaptive-simulation.md) |
| 4 | Enhancement | #5 Scene-Level, #6 Dialogue Subtext, #7 Thematic Resonance | 3h | DONE | [phase-04-enhancement-trio.md](phase-04-enhancement-trio.md) |
| 5 | Integration | Wire into orchestrator, update scoring | 2h | DONE | [phase-05-integration.md](phase-05-integration.md) |

## Dependencies
```
Phase 1 ──> Phase 2 ──> Phase 3 ──> Phase 4 ──> Phase 5
(schemas)   (knowledge)  (adaptive)   (enhance)   (wire)
```

## New Files Created
- `pipeline/layer2_enhance/psychology_engine.py` — Goal hierarchy, vulnerability map
- `pipeline/layer2_enhance/knowledge_system.py` — Per-character knowledge state
- `pipeline/layer2_enhance/causal_chain.py` — Causal event graph
- `pipeline/layer2_enhance/adaptive_intensity.py` — Feedback loop, dynamic rounds
- `pipeline/layer2_enhance/scene_enhancer.py` — Scene-level scoring + enhancement
- `pipeline/layer2_enhance/dialogue_subtext.py` — Says-vs-means dialogue layer
- `pipeline/layer2_enhance/thematic_tracker.py` — Theme extraction + motif tracking
- `services/prompts/layer2_enhanced_prompts.py` — All new Vietnamese prompts

## Key Constraints
- All modules optional/non-fatal (try-except fallback)
- File length < 200 lines per module
- Vietnamese-first prompts
- Reuse LLMClient, asyncio.to_thread patterns
- No breaking changes to existing pipeline

## Validation Summary

**Validated:** 2026-04-07
**Questions asked:** 6

### Confirmed Decisions
- **Psychology extraction**: 1 LLM call/character (parallel via asyncio.gather), not batched
- **Knowledge filtering**: Secret-only filtering (chỉ ẩn posts trực tiếp tiết lộ bí mật)
- **Scene-level enhancement**: Full scene-level (decompose + score + enhance weak scenes)
- **Execution strategy**: Full parallel all 5 phases using git worktree isolation + merge
- **Max simulation rounds**: 10 (thay vì 8 như plan gốc)
- **Merge strategy**: Worktree isolation per agent, merge về sau

### Action Items
- [ ] Update phase-03: MAX_ROUNDS = 10 (was 8)
- [ ] Implement with worktree isolation: mỗi phase 1 worktree riêng
- [ ] Ensure file ownership boundaries clear for conflict-free merges

## Risks
- LLM token cost increase from richer prompts (mitigate: use model_tier="cheap" for analysis)
- Simulation time increase from knowledge filtering (mitigate: cap knowledge items per agent)
- Scene decomposer already exists in L1 — reuse, don't duplicate
- Worktree merge conflicts on shared files (schemas.py, simulator.py, enhancer.py) — resolve sequentially
