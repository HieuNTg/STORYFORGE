---
phase: 1
title: "Character Psychology Engine"
status: completed
effort: 2.5h
depends_on: []
---

# Phase 1: Character Psychology Engine

## Context Links
- Plan: [plan.md](plan.md)
- Current agent: `pipeline/layer2_enhance/_agent.py` (188 lines)
- Schemas: `models/schemas.py` (Character, EmotionalState)
- Simulator: `pipeline/layer2_enhance/simulator.py` (DramaSimulator)

## Overview
Replace shallow EmotionalState (mood/energy/stakes) with a multi-dimensional psychology model. Add goal hierarchy, vulnerability map, and shame/fear triggers. Drama = vulnerability x pressure, not just mood x stakes.

## Key Insights
- Current `EmotionalState` has 3 scalars (mood, energy, stakes) and hardcoded `MOOD_TRIGGERS` (7 types)
- `Character` schema already has `secret`, `internal_conflict`, `breaking_point` — all unused in simulation
- `drama_multiplier` is `MOOD_DRAMA[mood] + stakes * (1-energy) * 0.5` — too simplistic
- Agents share identical emotional model — no character-specific psychology

## Requirements
1. Goal hierarchy per character: primary_goal, hidden_motive, fear, shame_trigger
2. Vulnerability map: emotional_wound -> who_can_exploit -> drama_multiplier
3. Psychology-aware drama_multiplier: vulnerability x pressure
4. Extract psychology from existing Character fields (motivation, internal_conflict, breaking_point, secret)
5. Non-breaking: old EmotionalState API preserved, psychology layered on top

## Architecture

### New file: `pipeline/layer2_enhance/psychology_engine.py` (~150 lines)

```python
class GoalHierarchy(BaseModel):
    primary_goal: str          # From Character.motivation
    hidden_motive: str         # From Character.secret or LLM-extracted
    fear: str                  # From Character.internal_conflict or LLM-extracted
    shame_trigger: str         # LLM-extracted from background + personality

class VulnerabilityEntry(BaseModel):
    wound: str                 # e.g., "bị bỏ rơi thời thơ ấu"
    exploiters: list[str]      # Character names who can trigger this
    drama_multiplier: float    # 1.0-3.0

class CharacterPsychology(BaseModel):
    character_name: str
    goals: GoalHierarchy
    vulnerabilities: list[VulnerabilityEntry]
    pressure: float = 0.0     # 0-1, accumulated from events targeting vulnerabilities
    defenses: list[str]       # Coping mechanisms: "phủ nhận", "tấn công", "rút lui"

class PsychologyEngine:
    def __init__(self): self.llm = LLMClient()

    def extract_psychology(self, character: Character, all_characters: list[Character]) -> CharacterPsychology:
        """LLM extracts goal hierarchy + vulnerabilities from Character fields."""

    def compute_drama_potential(self, psychology: CharacterPsychology) -> float:
        """Drama = avg(vulnerability.drama_multiplier) * pressure. Bounded [0.5, 3.0]."""

    def update_pressure(self, psychology: CharacterPsychology, event_type: str, attacker: str) -> None:
        """Increase pressure when event targets a vulnerability."""
```

### New schemas in `models/schemas.py`

Add after `EmotionalState` section (line ~266):
```python
class GoalHierarchy(BaseModel):
    primary_goal: str = ""
    hidden_motive: str = ""
    fear: str = ""
    shame_trigger: str = ""

class VulnerabilityEntry(BaseModel):
    wound: str = ""
    exploiters: list[str] = Field(default_factory=list)
    drama_multiplier: float = Field(default=1.5, ge=1.0, le=3.0)

class CharacterPsychology(BaseModel):
    character_name: str = ""
    goals: GoalHierarchy = Field(default_factory=GoalHierarchy)
    vulnerabilities: list[VulnerabilityEntry] = Field(default_factory=list)
    pressure: float = Field(default=0.0, ge=0, le=1)
    defenses: list[str] = Field(default_factory=list)
```

### Modified: `pipeline/layer2_enhance/_agent.py`

Add `psychology: CharacterPsychology | None = None` to `CharacterAgent.__init__`.
Update `drama_multiplier` property in `EmotionalState` to accept optional psychology override:
```python
# In CharacterAgent:
def get_drama_multiplier(self) -> float:
    if self.psychology:
        vuln_avg = sum(v.drama_multiplier for v in self.psychology.vulnerabilities) / max(1, len(self.psychology.vulnerabilities))
        return min(3.0, max(0.5, vuln_avg * self.psychology.pressure + self.emotion.drama_multiplier * 0.3))
    return self.emotion.drama_multiplier
```

### New prompt in `services/prompts/layer2_enhanced_prompts.py`

```python
EXTRACT_PSYCHOLOGY = """Phân tích tâm lý sâu của nhân vật sau:

TÊN: {name}
TÍNH CÁCH: {personality}
TIỂU SỬ: {background}
ĐỘNG LỰC: {motivation}
BÍ MẬT: {secret}
MÂU THUẪN NỘI TÂM: {internal_conflict}
ĐIỂM GÃY: {breaking_point}

CÁC NHÂN VẬT KHÁC: {other_characters}

Trả về JSON:
{{
  "primary_goal": "mục tiêu chính",
  "hidden_motive": "động cơ ẩn giấu",
  "fear": "nỗi sợ sâu nhất",
  "shame_trigger": "điều khiến nhân vật xấu hổ/mất kiểm soát",
  "vulnerabilities": [
    {{"wound": "vết thương tâm lý", "exploiters": ["tên nhân vật có thể khai thác"], "drama_multiplier": 2.0}}
  ],
  "defenses": ["cơ chế phòng vệ: phủ nhận/tấn công/rút lui/..."]
}}"""
```

## Related Code Files
- `pipeline/layer2_enhance/_agent.py` — CharacterAgent, EmotionalState (modify)
- `pipeline/layer2_enhance/simulator.py` — DramaSimulator.setup_agents (modify to call extract_psychology)
- `models/schemas.py` — add GoalHierarchy, VulnerabilityEntry, CharacterPsychology
- `services/prompts/layer2_enhanced_prompts.py` — new file for all L2 enhanced prompts

## Implementation Steps

1. **Add Pydantic schemas** to `models/schemas.py` (lines ~266): `GoalHierarchy`, `VulnerabilityEntry`, `CharacterPsychology` — 3 small models, ~25 lines total

2. **Create `pipeline/layer2_enhance/psychology_engine.py`**:
   - `PsychologyEngine.__init__()` — instantiate `LLMClient()`
   - `extract_psychology(character, all_characters) -> CharacterPsychology` — format EXTRACT_PSYCHOLOGY prompt with Character fields, call `llm.generate_json()`, parse into `CharacterPsychology`
   - `compute_drama_potential(psychology) -> float` — `avg(vuln.drama_multiplier) * pressure`, bounded [0.5, 3.0]
   - `update_pressure(psychology, event_type, attacker)` — if attacker in any vulnerability.exploiters, increase pressure by 0.15; if event_type matches wound keywords, increase by 0.1

3. **Create `services/prompts/layer2_enhanced_prompts.py`** with `EXTRACT_PSYCHOLOGY` prompt template (Vietnamese)

4. **Modify `_agent.py`**:
   - Import `CharacterPsychology` from schemas
   - Add `self.psychology: CharacterPsychology | None = None` in `CharacterAgent.__init__` (line 127)
   - Add `get_drama_multiplier()` method to `CharacterAgent` that blends psychology + emotion
   - Update `get_emotional_context()` to include psychology info when available

5. **Modify `simulator.py`**:
   - Import `PsychologyEngine` in `DramaSimulator.__init__` (non-fatal)
   - In `setup_agents()` (line 97): after creating agents, call `psychology_engine.extract_psychology()` for each character, assign to `agent.psychology`
   - In `_apply_escalation()` (line 434): use `agent.get_drama_multiplier()` instead of `agent.emotion.drama_multiplier`
   - In `simulate_round()` post-round updates: call `psychology_engine.update_pressure()` when events target a character

6. **Update `services/prompts/__init__.py`**: import and re-export `EXTRACT_PSYCHOLOGY`

## Todo
- [x] Add GoalHierarchy, VulnerabilityEntry, CharacterPsychology to schemas.py
- [x] Create psychology_engine.py with PsychologyEngine class
- [x] Create layer2_enhanced_prompts.py with EXTRACT_PSYCHOLOGY
- [x] Add psychology field to CharacterAgent
- [x] Add get_drama_multiplier() to CharacterAgent
- [x] Wire extract_psychology into DramaSimulator.setup_agents
- [x] Wire update_pressure into simulate_round post-round updates
- [x] Update _apply_escalation to use get_drama_multiplier
- [x] Update prompts/__init__.py exports

## Success Criteria
- `PsychologyEngine.extract_psychology()` returns valid `CharacterPsychology` for any Character
- `drama_multiplier` now varies per-character based on vulnerability x pressure
- Existing pipeline runs unchanged when psychology extraction fails (fallback to old multiplier)
- Psychology data visible in agent prompt context

## Risk Assessment
- **LLM cost**: One extra LLM call per character at simulation start (~5 calls). Mitigate: use `model_tier="cheap"`.
- **Latency**: Psychology extraction is one-time setup. Mitigate: run all extractions in parallel with `asyncio.gather`.
- **Bad LLM output**: Mitigate: try-except with fallback to empty CharacterPsychology.

## Security Considerations
- No user input directly in prompts beyond story data already in pipeline
- No file I/O or network calls beyond existing LLM client

## Next Steps
Phase 2 uses psychology data to build knowledge asymmetry and causal chains.
