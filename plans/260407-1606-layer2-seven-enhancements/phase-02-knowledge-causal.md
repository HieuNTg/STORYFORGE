---
phase: 2
title: "Secret/Knowledge System + Causal Event Chain"
status: completed
effort: 2.5h
depends_on: [1]
---

# Phase 2: Secret/Knowledge System + Causal Event Chain

## Context Links
- Plan: [plan.md](plan.md)
- Phase 1: [phase-01-psychology-engine.md](phase-01-psychology-engine.md)
- Simulator: `pipeline/layer2_enhance/simulator.py`
- Agent: `pipeline/layer2_enhance/_agent.py`
- Schemas: `models/schemas.py` (CharacterState.knowledge, SimulationEvent)

## Overview
Two tightly coupled enhancements: (1) per-character knowledge state so agents only see what they know, enabling dramatic irony and revelation timing; (2) causal event graph replacing flat event lists with cause-effect chains.

## Key Insights
- `Character.secret` field exists but is NEVER used in simulation — agents see all posts equally
- `_get_recent_posts()` (simulator.py:113) shows ALL posts to ALL agents — no information asymmetry
- `CharacterState.knowledge[]` exists in schema but is only populated by L1, never used in L2
- `SimulationEvent` has no `cause_event_id` or `triggered_by` field — events are independent
- Enhancer filters top 5 events as flat bullet list — no causal structure passed to enhancement

## Requirements
1. Per-character knowledge registry: who knows what facts
2. Secret registration: Character.secret becomes a trackable knowledge item
3. Knowledge filtering in `_get_recent_posts()`: agents only see posts they should know about
4. Revelation mechanics: when a secret surfaces, propagate knowledge to witnesses
5. Dramatic irony flag: mark when reader knows but character doesn't
6. Causal event graph: each SimulationEvent can reference a `cause_event_id`
7. Consequence tracking: events have `consequences: list[str]`
8. Causal chain text for enhancer: events formatted as chains, not flat lists

## Architecture

### New file: `pipeline/layer2_enhance/knowledge_system.py` (~160 lines)

```python
class KnowledgeItem(BaseModel):
    fact_id: str               # Unique ID
    content: str               # The fact/secret
    known_by: list[str]        # Character names who know this
    source: str                # "initial" | "revealed" | "witnessed"
    revealed_round: int = 0    # When it became known (0 = from start)
    is_secret: bool = False
    dramatic_irony: bool = False  # Reader knows, some characters don't

class KnowledgeRegistry:
    def __init__(self): self.items: dict[str, KnowledgeItem] = {}

    def register_secret(self, character: Character) -> None:
        """Register Character.secret as a KnowledgeItem known only to that character."""

    def character_knows(self, char_name: str, fact_id: str) -> bool

    def reveal_to(self, fact_id: str, char_name: str, round_num: int) -> None
        """Reveal a fact to a character. Updates known_by."""

    def get_visible_posts(self, char_name: str, all_posts: list[AgentPost], limit: int = 5) -> list[AgentPost]:
        """Filter posts: exclude those referencing secrets the character doesn't know."""

    def get_knowledge_context(self, char_name: str) -> str:
        """Format what this character knows for prompt injection."""

    def check_revelation_triggers(self, posts: list[AgentPost], round_num: int) -> list[dict]:
        """Detect when a post reveals a secret. Returns revelation events."""
```

### New file: `pipeline/layer2_enhance/causal_chain.py` (~130 lines)

```python
class CausalEvent(BaseModel):
    event_id: str
    cause_event_id: str = ""       # ID of triggering event (empty = root cause)
    event: SimulationEvent         # The actual event data
    consequences: list[str] = Field(default_factory=list)
    forces_choice_for: list[str] = Field(default_factory=list)  # Characters forced to decide

class CausalGraph:
    def __init__(self): self.events: dict[str, CausalEvent] = {}

    def add_event(self, event: SimulationEvent, cause_id: str = "") -> str:
        """Add event to graph, return generated event_id."""

    def add_consequence(self, event_id: str, consequence: str) -> None

    def get_chain(self, event_id: str) -> list[CausalEvent]:
        """Walk backward from event to root cause, return chain."""

    def get_roots(self) -> list[CausalEvent]:
        """Events with no cause (root triggers)."""

    def format_causal_text(self) -> str:
        """Format for enhancer prompt: 'A -> triggers B -> forces C to choose'."""

    def get_top_chains(self, n: int = 5) -> list[list[CausalEvent]]:
        """Return N highest-drama chains sorted by cumulative drama_score."""
```

### Schema additions in `models/schemas.py`

```python
# Add to SimulationEvent:
class SimulationEvent(BaseModel):
    # ... existing fields ...
    cause_event_id: str = Field(default="", description="ID of event that caused this one")
    consequences: list[str] = Field(default_factory=list, description="What this event caused")

# Add to SimulationResult:
class SimulationResult(BaseModel):
    # ... existing fields ...
    knowledge_state: dict[str, list[str]] = Field(default_factory=dict, description="Per-character knowledge at end")
    causal_chains: list[list[str]] = Field(default_factory=list, description="Top causal chains as event_id lists")
```

## Related Code Files
- `pipeline/layer2_enhance/simulator.py` — `_get_recent_posts()`, `simulate_round()`, `evaluate_drama()`
- `pipeline/layer2_enhance/_agent.py` — `CharacterAgent.memory`, `add_memory()`
- `models/schemas.py` — `SimulationEvent`, `SimulationResult`, `Character`
- `pipeline/layer2_enhance/enhancer.py` — `enhance_chapter()` events_text formatting

## Implementation Steps

1. **Add schema fields** to `models/schemas.py`:
   - `SimulationEvent`: add `cause_event_id: str = ""` and `consequences: list[str] = Field(default_factory=list)`
   - `SimulationResult`: add `knowledge_state: dict[str, list[str]] = Field(default_factory=dict)` and `causal_chains: list[list[str]] = Field(default_factory=list)`

2. **Create `pipeline/layer2_enhance/knowledge_system.py`**:
   - `KnowledgeRegistry.__init__()` — empty dict of `KnowledgeItem`
   - `register_secret(character)` — if `character.secret`, create `KnowledgeItem(fact_id=f"secret_{character.name}", content=character.secret, known_by=[character.name], is_secret=True)`
   - `register_initial_knowledge(characters, relationships)` — register public relationship info as known by both parties
   - `character_knows(char_name, fact_id)` — lookup in items
   - `reveal_to(fact_id, char_name, round_num)` — append char_name to known_by, set revealed_round
   - `get_visible_posts(char_name, all_posts, limit=5)` — filter posts whose content references a secret not known by char_name. Use simple substring matching on secret content keywords.
   - `get_knowledge_context(char_name)` — return formatted string of facts known by char_name
   - `check_revelation_triggers(posts, round_num)` — scan posts for secret content keywords; if found and poster knows the secret, reveal to all agents in the post's target + witnesses

3. **Create `pipeline/layer2_enhance/causal_chain.py`**:
   - `CausalGraph.__init__()` — empty dict
   - `add_event(event, cause_id)` — generate `event_id = f"evt_{event.round_number}_{len(self.events)}"`, wrap in `CausalEvent`, store in dict
   - `add_consequence(event_id, consequence)` — append to event's consequences list
   - `get_chain(event_id)` — follow cause_event_id links backward, return list
   - `get_roots()` — events where cause_event_id is empty
   - `format_causal_text()` — for each root, walk forward building "A -> triggers B -> forces C" strings
   - `get_top_chains(n=5)` — sort chains by sum of drama_scores, return top N

4. **Modify `simulator.py`**:
   - Import `KnowledgeRegistry` and `CausalGraph`
   - In `__init__()`: add `self.knowledge = KnowledgeRegistry()` and `self.causal_graph = CausalGraph()`
   - In `setup_agents()`: call `self.knowledge.register_secret(c)` for each character
   - In `_get_recent_posts()` (line 113): replace direct filter with `self.knowledge.get_visible_posts(exclude_agent, self.all_posts, limit)` — wrap in try-except, fallback to current behavior
   - In `simulate_round()` post-round (line 334): call `self.knowledge.check_revelation_triggers(round_posts, round_number)` to detect and propagate revelations
   - In `evaluate_drama()` event extraction (line 509): when creating `SimulationEvent`, try to link `cause_event_id` by matching `characters_involved` with prior events. Call `self.causal_graph.add_event(event, cause_id)`
   - In `run_simulation()` result building (line 553): add `knowledge_state` and `causal_chains` to SimulationResult

5. **Modify `enhancer.py`** `enhance_chapter()`:
   - After building `events_text` (line 57): if `sim_result.causal_chains` exists, format as causal chain text instead of flat bullet list
   - New helper: `_format_causal_events(sim_result, chapter_number)` — use `CausalGraph.format_causal_text()` pattern

6. **Add prompt** `KNOWLEDGE_AWARE_AGENT` to `services/prompts/layer2_enhanced_prompts.py`:
   ```
   KNOWLEDGE_AWARE_AGENT = """... {known_facts} ... {unknown_secrets_count} bí mật bạn chưa biết ..."""
   ```

7. **Update `services/prompts/__init__.py`**: import and export new prompts

## Todo
- [ ] Add cause_event_id, consequences to SimulationEvent schema
- [ ] Add knowledge_state, causal_chains to SimulationResult schema
- [ ] Create knowledge_system.py with KnowledgeRegistry
- [ ] Create causal_chain.py with CausalGraph
- [ ] Wire KnowledgeRegistry into simulator.setup_agents
- [ ] Replace _get_recent_posts with knowledge-filtered version
- [ ] Wire revelation detection into simulate_round
- [ ] Wire CausalGraph into evaluate_drama event creation
- [ ] Update enhancer to use causal chain text
- [ ] Add KNOWLEDGE_AWARE_AGENT prompt

## Success Criteria
- Agents only see posts consistent with their knowledge state
- Character.secret is registered and tracked through simulation
- Secret revelations generate high-drama events automatically
- Events have cause_event_id linking them into chains
- Enhancer receives causal chain text instead of flat event lists
- Pipeline continues normally if knowledge_system or causal_chain fails

## Risk Assessment
- **Knowledge filtering too aggressive**: Agents might miss important context. Mitigate: only filter secret-related posts, not all posts.
- **Causal linking false positives**: LLM might incorrectly link unrelated events. Mitigate: only link events sharing 2+ characters in common within same/adjacent rounds.
- **Performance**: Knowledge filtering adds string matching per post. Mitigate: cap to last 20 posts, simple keyword match.

## Security Considerations
- No new external dependencies or I/O
- Knowledge items contain story content only

## Next Steps
Phase 3 uses drama scores from causal chains to drive adaptive simulation intensity.
