# Test Plan — Sprint 1 (the 14 P0 defects)

Scope: verifying the four batches committed on `sprint/comic-quality-and-qwen-provider`
(`507ebdf`, `6e24793`, `6dc0127`, `19ee3d9`).

**Method.** Every P0 fix ships with a regression test that was *run against the
parent commit and observed to fail* before the fix landed — not merely written
after the fact. Those pre-fix failure counts are recorded below. The remaining
sections are the verification this plan asks the CEO to approve: the parts that
automated tests cannot reach on their own.

---

## 1. Automated regression tests (written and passing)

| Batch | File | Tests | Failed pre-fix |
| --- | --- | --- | --- |
| A1 · craft lane | `tests/test_agent_lane_config.py` | 6 | 5 |
| A2 · contract gate | `tests/test_contract_gate_regression.py` | 7 | 5 |
| A3 · L2 degradation | `tests/test_simulator_degrade.py` | 6 | 6 |
| A4 · validation error | `tests/test_validation_error_vs_failure.py` | 6 | 6 |
| B1 · dotenv + secrets | `tests/test_dotenv_and_secrets.py` | 13 | all (collection) |
| B2 · config round-trip | `tests/test_config_persistence_roundtrip.py` | 21 | 11 |
| B3 · per-run flags | `tests/test_run_config_overrides.py` | 7 | all (collection) |
| C1 · library quota | `frontend/stores/library-store.persist.test.ts` | 6 | 6 |
| C2 · recovery backoff | `frontend/lib/sse/useRunRecovery.backoff.test.ts` | 3 | 1 |
| D1 · resume | `tests/test_resume_completeness.py` | 8 | all (collection) |
| D2 · cache key | `tests/test_llm_cache_key.py` | 9 | 3 |
| D3 · provider timeouts | `tests/test_provider_timeouts.py` | 7 | 6 |
| D4 · comic alignment | `tests/test_comic_panel_alignment.py` | 5 | 2 |
| **Total** | | **104** | |

Three pre-existing tests were changed deliberately, each because it encoded the
behaviour being fixed. Flagged here because they are the assertions most worth a
second opinion:

- `tests/test_contract_gate.py` asserted `chapters_checked == 1` for a chapter
  with **no** contract — i.e. it pinned the false-green metric. Now asserts the
  chapter is counted as skipped.
- `tests/test_flowkit.py` asserted `flowkit_callback_hmac_required is False`.
  Flipped to on, because the callback route is now CSRF-exempt and the body
  signature is the only thing authenticating it.
- `tests/test_pipeline_core_coverage.py` (existing) still asserts failures are
  dropped from `generate_story_images` — kept, since that is the default
  contract; position-preserving behaviour is opt-in via `keep_positions`.

## 2. Full-suite gate

- [x] `scripts/run_gate_chunks.ps1` with `STORYFORGE_DISABLE_REAL_EMBEDDINGS=1`.
      4867 passed, 0 failed, 6 skipped. EXIT1/2/3/5 = 0.
      **EXIT4 = 5 is pre-existing**: chunk 4 points at directories that contain
      no `test_*.py`, so it collects nothing. Tracked as Phase 3 work, unrelated
      to this sprint.
- [x] Combined coverage **74%**, up from the 70% baseline.
- [x] `npx tsc --noEmit` clean; `npx vitest run` green (145 tests).
- [x] `python -m ruff check .` clean.

## 3. Manual verification — things tests cannot prove

These are what the CEO or I should exercise against a running instance. Ordered
by how much of the sprint's value they confirm.

### 3.1 The craft lane actually produces reviews (A1)
- [ ] Run a short story (2-3 chapters) with default settings.
- [ ] Confirm the progress log shows the agent panel running on Layer 2 and
      `output.reviews` is non-empty in the result summary.
- [ ] Confirm no `[AGENTS] WARN` / `[AGENTS] ERROR` line appears.
- **Why manual:** the unit test drives a mocked panel. Only a real run proves the
  8 agents and the debate execute end-to-end against a live provider.

### 3.2 Secrets are encrypted at rest, and nothing is locked out (B1)
- [ ] Back up `data/config.json` first.
- [ ] Start the server; confirm the one-time migration warning appears.
- [ ] Confirm `data/config.json` now shows `ENC:` prefixes on key fields.
- [ ] Restart and confirm the Settings page still shows the masked keys and a
      generation run still authenticates.
- **Risk to confirm:** these values are only recoverable with the current
  `STORYFORGE_SECRET_KEY`. If `.env` is lost, the keys must be re-entered.
  **Please confirm `.env` is backed up before this step.**

### 3.3 Env overrides now take effect (B1, behaviour change)
- [ ] Confirm the values in `.env` are the ones intended to win over
      `data/config.json` — all 30 `_ENV_MAP` entries were dead before and are
      live now. `STORYFORGE_API_KEY`, `STORYFORGE_BASE_URL` and
      `STORYFORGE_MODEL` are the ones that change behaviour most visibly.

### 3.4 Settings survive a restart (B2)
- [ ] Change an `l2_*` value and an advanced toggle in Settings, save, restart
      the server, confirm both persist. Every one of these reverted before.

### 3.5 Library quota failure is honest (C1)
- [ ] In DevTools, fill localStorage close to quota, then finish a run.
- [ ] Confirm an error toast appears (not a success toast) and the existing
      library survives a reload.

### 3.6 A dropped stream reattaches (C2)
- [ ] Start a run, kill the network briefly (DevTools offline), restore it.
- [ ] Confirm the UI reattaches without a manual page reload.
- [ ] Press Cancel on another run and confirm it does **not** come back and
      auto-save itself.

### 3.7 Comic pages stay aligned when a panel fails (D4)
- [ ] Generate a comic chapter with a provider that occasionally drops a panel
      (or force one failure).
- [ ] Confirm the failed panel renders as a placeholder in its own cell and every
      later panel is still in the right cell, with dialogue on the right art.
- **Why manual:** this is a visual defect. The unit test proves list alignment;
  only looking at the page proves the balloons land correctly.

### 3.8 Resume refuses a half-written story (D1)
- [ ] Interrupt a run mid-generation, then resume from its checkpoint.
- [ ] Confirm it reports `N/M chương` and does not produce a "finished" story
      shorter than the outline.

## 4. Known gaps — deliberately out of Sprint 1

Recorded so review does not mistake them for oversights. Each is tracked in
`IMPLEMENTATION_PLAN.md`.

- **Concurrent runs still share config.** 26 modules read the `ConfigManager`
  singleton directly, so overlapping runs with different flags remain
  last-writer-wins. A run no longer dictates the *next* one, which was the
  data-integrity half. Full isolation needs a contextvar-scoped config.
- **Library ceiling unchanged.** Quota failure is now reported honestly rather
  than losing the shelf; moving prose to IndexedDB to raise the ceiling is a
  storage-layer change.
- **Recovery replay is still noisy.** A reload at chapter 12 pops 12 toasts.
  Noisy, not destructive — `addStory` upserts by id.
- **"Viết tiếp" has no recovery.** Needs the continue endpoints to expose a
  session id first.
- **Partial L1 does not restart from its last batch.** Resume now refuses to
  advance an incomplete draft; continuing it is a change to the batch
  generator's entry contract.

## 5. Test results

| Item | Status | Notes |
| --- | --- | --- |
| Batch A regression tests | PASS | 25 tests; 367 L2/agent tests green |
| Batch B regression tests | PASS | 41 tests; 349 config/API tests green |
| Batch C regression tests | PASS | 9 tests; 145 frontend tests green, tsc clean |
| Batch D regression tests | PASS | 29 tests; 247 media/LLM tests green |
| Full-suite gate | PASS | 4867 passed, 0 failed, 6 skipped across chunks 1-3; EXIT1/2/3/5 = 0 |
| Combined coverage | PASS | 74%, up from the 70% baseline |
| Manual verification §3 | PENDING | awaiting CEO approval of this plan |
