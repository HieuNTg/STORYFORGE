# Research: Layer 2 Agent/Simulator/Analyzer/DramaPatterns

## 1. `_agent.py` — CharacterAgent, EmotionalState, TrustEdge

### Classes
- **EmotionalState** (L32-83) — tracks mood, energy (0-1), stakes (0-1), mood_history, arc_trajectory
  - `drama_multiplier` property: `MOOD_DRAMA[mood] + stakes*(1-energy)*0.5`, bounded [0.5, 3.0]
  - `update_mood(event_type)` uses MOOD_TRIGGERS dict (7 mappings)
  - `record_round()` appends to arc_trajectory for post-sim analysis
- **TrustEdge** (L86-115) — directed trust 0-100, history list
  - `is_betrayal_trigger`: checks if last delta > 30 points drop
- **CharacterAgent** (L118-187) — wraps Character schema + memory + emotion + trust_map
  - `memory`: list[str] capped at 50 via importance-scored pruning
  - `_score_importance()`: keyword match (escalation=1.0, self-mention=0.8, else=0.5)
  - `process_event()`: updates mood + stakes/energy based on is_target flag
  - `get_emotional_context()`: formats emotion+trust for prompt injection

### Data constants
- `TENSION_DELTAS` (L6-10): 9 relationship types -> float delta
- `MOOD_DRAMA` (L13-18): 10 moods -> drama multiplier (1.0-1.8)
- `MOOD_TRIGGERS` (L21-29): 7 event_type -> mood mappings

### Limitations
- **No secrets/knowledge model** — agents have flat memory list, no private vs public knowledge
- **No causal chains** — memory is append-only text, no event->consequence linking
- **Mood triggers are hardcoded** — only 7 event types mapped, LLM-generated event_types often miss
- **No personality-driven mood response** — all characters react identically to same event type
- **Trust is per-agent only** — no global reputation or group dynamics
- **Memory pruning is simplistic** — keyword-based scoring, no semantic relevance

---

## 2. `simulator.py` — DramaSimulator

### Classes
- **TrustNetworkEdge** (L56-77) — simulator-level pairwise trust (separate from agent TrustEdge)
  - `is_betrayal_candidate`: trust < 30
- **DramaSimulator** (L79-608) — main simulation engine

### Key Methods
| Method | Line | Purpose |
|--------|------|---------|
| `setup_agents()` | L97 | Creates CharacterAgent per character, initializes trust network from relationships |
| `simulate_round()` | L274 | Runs all agents in parallel (asyncio+executor), applies state mutations sequentially |
| `_run_single_agent()` | L154 | LLM call per agent per round; returns AgentPost + metadata (new_mood, trust_change) |
| `_generate_reactions()` | L204 | Multi-layer reaction chain; targeted chars react to posts |
| `_run_reaction()` | L239 | Single reaction LLM call |
| `evaluate_drama()` | L377 | LLM evaluates round drama, returns events + relationship_changes |
| `_check_escalation()` | L399 | Checks tension thresholds adjusted by genre curve + intensity |
| `_apply_escalation()` | L434 | LLM generates escalation event, score boosted by pattern multiplier * agent drama_multiplier |
| `run_simulation()` | L476 | Main loop: N rounds of simulate->evaluate->escalate->update |
| `_update_relationship()` | L567 | Applies relationship type changes + syncs trust network |
| `_generate_suggestions()` | L590 | Post-sim LLM call for drama suggestions |

### Data flow
```
run_simulation(characters, relationships, genre, num_rounds)
  -> setup_agents() 
  -> for each round:
       simulate_round() -> _run_single_agent() x N agents (parallel)
                        -> _generate_reactions() (multi-layer)
       evaluate_drama() -> LLM evaluation
       _check_escalation() -> _apply_escalation() if triggered
       _update_relationship() from evaluation
       record_round() on all agents
  -> _generate_suggestions()
  -> SimulationResult
```

### Configuration
- `INTENSITY_CONFIG` (L23-27): 3 levels (thap/trung binh/cao) controlling temperature, escalation_scale, max_escalations, reaction_depth
- `ESCALATION_PATTERNS` (L34-40): 5 patterns with trigger_tension + intensity_multiplier
- `ESCALATION_VALID_RELATIONS` (L44-50): constrains which patterns fire for which relationship types

### Limitations
- **Duplicate trust systems** — TrustNetworkEdge (simulator) vs TrustEdge (agent) are independent, partially synced
- **No secret/knowledge propagation** — agents see all posts, no information asymmetry
- **Reaction depth is random** — layers 1+ have random skip probability (50%/70%), not story-driven
- **No causal chain tracking** — events are independent, no "this happened because of that"
- **Escalation is threshold-only** — no narrative logic, just tension >= threshold
- **No adaptive round count** — fixed num_rounds, no early termination or extension based on drama state
- **Agent memory context is tiny** — only last 3 memories injected into prompt
- **No character goals/plans** — agents are purely reactive, no proactive scheming

---

## 3. `analyzer.py` — StoryAnalyzer

### Classes
- **StoryAnalyzer** (L11-106) — analyzes draft to extract relationships + conflict graph

### Key Methods
| Method | Line | Purpose |
|--------|------|---------|
| `analyze()` | L20 | LLM extracts relationships, conflict_points, untapped_drama, character_weaknesses from draft |
| `extract_conflict_graph()` | L71 | Per-chapter: extracts goal/obstacle/conflict via LLM, calculates tension_score |
| `_calc_tension()` | L98 | Cumulative tension: base 0.3 if conflict exists + exponential escalation from unresolved count |

### Data flow
- Input: `StoryDraft` (title, genre, characters, chapters, synopsis)
- Output of `analyze()`: `{relationships: [Relationship], conflict_points: [], untapped_drama: [], character_weaknesses: {}}`
- Output of `extract_conflict_graph()`: `[{chapter, goal, obstacle, conflict, tension_score}]`

### Limitations
- **No character psychology extraction** — only gets weaknesses as flat dict from LLM
- **Conflict graph is per-chapter only** — no cross-chapter causal links
- **Tension calc ignores content** — purely structural (count of unresolved conflicts)
- **No secret/knowledge extraction** — doesn't identify what characters know/don't know
- **Synopsis fallback is naive** — first 300 chars per chapter, may miss key info

---

## 4. `drama_patterns.py` — Genre Patterns + Tension Curves

### Data
- `GENRE_DRAMA_RULES` (L4-58): 8 Vietnamese genres with genre-specific flags
  - Fields vary: `tension_curve`, `key_patterns`, plus genre-specific booleans (power_escalation, faction_dynamics, etc.)
  - Tension curves: "ascending", "oscillating", "wave"

### Functions
| Function | Line | Purpose |
|----------|------|---------|
| `get_genre_rules()` | L61 | Fuzzy genre lookup, returns rules dict |
| `get_tension_modifier()` | L72 | Position-based modifier for escalation threshold; <1 = easier, >1 = harder |
| `get_genre_escalation_prompt()` | L98 | Generates genre-specific text instructions for simulation prompts |

### Tension curves
- ascending: `1.2 - pos*0.5` (1.2 -> 0.7, easier over time)
- oscillating: `1.0 - 0.3*sin(pos*2pi)` (peaks at 25%/75%)
- wave: `1.0 - 0.2*sin(pos*3pi)` (gentler oscillation)

### Limitations
- **Genre rules are static config** — not adaptive, no learning from story content
- **Tension curves are simple math** — no awareness of actual story beats
- **key_patterns are unused in simulation** — listed but never checked/enforced during agent behavior
- **No support for multi-genre** — single genre lookup only
- **escalation_interval, emotional_cadence etc. are declared but never read** by simulator

---

## Integration Map

```
StoryAnalyzer.analyze(draft) 
  -> relationships, conflict_points
     |
     v
DramaSimulator.run_simulation(characters, relationships, genre)
  uses: CharacterAgent (per character)
        drama_patterns.get_genre_escalation_prompt() -- per round
        drama_patterns.get_tension_modifier() -- in _check_escalation
  outputs: SimulationResult
```

### Cross-cutting gaps
1. **Two trust systems** not fully synced (agent-level TrustEdge vs simulator TrustNetworkEdge)
2. **No knowledge/secret layer** anywhere in pipeline
3. **No causal chain** connecting analyzer conflicts -> simulation events -> output
4. **Genre-specific rules partially wired** — tension_curve and key_patterns used in prompts but genre-specific flags (faction_dynamics etc.) only generate prompt text, don't alter simulation mechanics
5. **Agent psychology is shallow** — mood + energy + stakes, no beliefs/goals/fears/secrets
6. **Memory is flat text** — no structured event graph, no information asymmetry
