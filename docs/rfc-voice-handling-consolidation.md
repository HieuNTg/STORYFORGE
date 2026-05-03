# RFC: Voice Handling Consolidation (H1/H2)

**Status:** Phase A landed (nested VoiceConfig + sync). Phase B/C pending CEO greenlight.
**Date:** 2026-05-03
**Author:** Engineering Squad (autonomous)
**Tracking audit:** `plans/reports/agency-orchestrator-260503-1330-project-audit.md` H1, H2

---

## Problem

Voice handling spans **8 config flags + 2 modules** with overlapping concerns. New contributors can't tell which flag controls which path; defaults are inconsistent (some thresholds, some booleans, all at root level of `PipelineConfig`).

### Current surface

**Flags** (`config/defaults.py`):

| Flag | Default | Concern |
|------|---------|---------|
| `enable_voice_contract` | True | Build per-chapter voice contracts from L1 profiles |
| `enable_voice_contract_retry` | True | Refine-with-hint on drift vs. binary revert |
| `voice_min_compliance` | 0.75 | Pass threshold per chapter |
| `voice_dedup_l1_l2` | True | Skip L2 re-extract when L1 profile present |
| `voice_binary_revert_floor` | 0.5 | Last-resort revert threshold |
| `l2_voice_preservation` | True | Master enable for L2 voice gate |
| `l2_voice_drift_threshold` | 0.4 | Drift warning threshold |
| `l2_voice_revert_threshold` | 0.3 | Auto-revert threshold |

**Modules**:

- `pipeline/layer1_story/character_voice_profiler.py` — L1 generates `voice_profiles`
- `pipeline/layer2_enhance/voice_fingerprint.py` — L2 validates against profiles

Both touch the same conceptual entity (per-character voice signature) but live in separate layers with no shared service.

---

## Goals

1. Single config namespace — one `voice_config: VoiceConfig` nested dataclass
2. Single source of truth — extract shared logic to `services/voice_engine.py`
3. No behavior change — defaults preserve current runtime
4. Minimal migration — keep flat-flag accessors via property shims for one release

## Non-goals

- Rewriting voice fingerprint algorithm
- Changing voice schema (`draft.voice_profiles` stays)
- Touching the multi-agent voice consistency debate

---

## Proposed shape

### 1. Nested config

```python
# config/defaults.py
@dataclass
class VoiceConfig:
    # Generation (L1)
    dedup_l1_l2: bool = True

    # Validation (L2)
    enabled: bool = True                  # was l2_voice_preservation
    min_compliance: float = 0.75
    drift_warn_threshold: float = 0.4     # was l2_voice_drift_threshold
    drift_revert_threshold: float = 0.3   # was l2_voice_revert_threshold
    binary_revert_floor: float = 0.5

    # Contract gate
    contract_enabled: bool = True         # was enable_voice_contract
    contract_retry_enabled: bool = True   # was enable_voice_contract_retry


@dataclass
class PipelineConfig:
    ...
    voice: VoiceConfig = field(default_factory=VoiceConfig)
```

### 2. Shared service

```
services/voice_engine.py
├── extract_profile(character, chapters) -> VoiceProfile   # used by L1
├── score_compliance(chapter, profiles) -> float           # used by L2
├── drift_diff(profile_a, profile_b) -> float              # used by L2
└── build_contract(profiles, outline) -> VoiceContract     # used by L2
```

L1's `character_voice_profiler.py` shrinks to a thin wrapper around `voice_engine.extract_profile`. L2's `voice_fingerprint.py` shrinks to a wrapper around `score_compliance` + `drift_diff`.

### 3. Migration path (one release)

Phase A — additive (no breaking change):
1. Add `VoiceConfig` dataclass + `pipeline.voice` field
2. Add property shims on `PipelineConfig` so `cfg.l2_voice_preservation` still works (reads `cfg.voice.enabled`)
3. Update `config/presets.py` writers to set both old + new
4. Extract `services/voice_engine.py` (call sites still hit old modules but they delegate)

Phase B — deprecation:
5. Update all call sites to read `cfg.voice.*`
6. Mark old flags `@deprecated` in docstrings, log warning when set explicitly
7. Update UI/API to send nested shape (form change)

Phase C — removal (next major version):
8. Delete property shims + old flat flags
9. Delete the now-empty wrapper modules

---

## Risks

- **Checkpoint compatibility** — old checkpoints serialize `PipelineConfig` flat. Mitigation: `__post_init__` migration that promotes flat fields into `voice` if present.
- **UI form** — frontend posts flat keys. Mitigation: API route layer translates `voice_*` → `voice.{*}` for one release.
- **Preset diff churn** — every preset file gets touched. Mitigation: scripted rewrite + golden-test snapshots.
- **Test churn** — voice tests hit specific flag names. Mitigation: keep shims through Phase B.

---

## Estimate

- Phase A: 1 day (config + service extract, no call-site changes)
- Phase B: 2 days (migrate all call sites + UI/API)
- Phase C: 0.5 day (delete shims)

Total: ~3.5 dev-days, low risk if Phase A lands first behind shims.

---

## Resolved questions (2026-05-03)

1. **Inline in `defaults.py`** — canonical config home, KISS.
2. **Stateless module functions** — easier to test; engine has no cross-call state.
3. **UI form** — flat keys preserved through Phase B; collapse to nested accordion in Phase C.
4. **Phased rollout** — Phase A landed this sprint; Phase B/C deferred.

## Phase A — landed scope

- `VoiceConfig` dataclass added inline in `config/defaults.py`
- `PipelineConfig.voice` field with `__post_init__` sync from flat fields
- Flat fields (`l2_voice_preservation`, `voice_min_compliance`, …) remain authoritative — zero call-site changes required
- Verified: 57/57 regression tests pass; custom flat overrides flow into nested view

## Phase A note on H2 (code dedup)

After re-reading both modules, the H2 audit finding is largely a **false positive**:

- `pipeline/layer1_story/character_voice_profiler.py` (207 LOC) → LLM-driven *generation*
- `pipeline/layer2_enhance/voice_fingerprint.py` (680 LOC) → algorithmic *analysis + enforcement*

Different concerns, no shared algorithm to extract. Phase B will revisit only if a true shared primitive emerges.
