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
      4883 passed, 0 failed, 6 skipped. EXIT1/2/3/5 = 0.
      **EXIT4 = 5 is pre-existing**: chunk 4 points at directories that contain
      no `test_*.py`, so it collects nothing. Tracked as Phase 3 work, unrelated
      to this sprint.
- [x] Combined coverage **74%**, up from the 70% baseline.
- [x] `npx tsc --noEmit` clean; `npx vitest run` green (145 tests).
- [x] `python -m ruff check .` clean.

## 3. Manual verification — things tests cannot prove

These are what the CEO or I should exercise against a running instance. Ordered
by how much of the sprint's value they confirm.

### 3.1 The craft lane actually produces reviews (A1) — **VERIFIED**
Covered by `tests/test_craft_lane_integration.py`, which drives the real
`AgentRegistry`, the real agent classes and the real `DebateOrchestrator`,
mocking only at the `LLMClient` boundary — no provider calls, no tokens spent.
- [x] Layer-2 panel returns reviews on the default config.
- [x] Every registered layer-2 role is heard from (not a partial panel).
- [x] Causal link proven: deleting `debate_mode` from `PipelineConfig` at runtime
      reproduces `AttributeError: type object 'PipelineConfig' has no attribute
      'debate_mode'` — the exact failure that was being swallowed.
- Remaining for a live run: end-to-end behaviour against a real provider. The
  wiring is proven; only response quality is unverified.

### 3.2 Secrets at rest (B1) — **RUN, THEN DELIBERATELY REVERTED**
- [x] Backed up `data/config.json` and `.env` before touching anything.
- [x] Migration ran, encrypted the keys, and the round-trip decrypted back to
      the exact original plaintext (sha match).
- [x] **Then found the key was `change-me-in-production`** — the placeholder the
      repo ships. Encrypting with a publicly known key is worse than plaintext:
      anyone with the file can read it, while the `ENC:` prefix makes it look
      protected. The migration was reverted from the backup.
- [x] `secret_manager` now refuses any template placeholder key and logs why, so
      the product can no longer fake encryption.
- **Still open for the CEO:** set a real `STORYFORGE_SECRET_KEY` in `.env` to
  actually enable secrets at rest. Until then keys stay in plaintext, which is
  at least honest. Once set, back the key up — the values are unrecoverable
  without it.

### 3.3 Env overrides (B1) — **VERIFIED, AND A HAZARD WAS FIXED**
- [x] 7 of 29 `_ENV_MAP` entries are live from `.env`; 4 differ from
      `data/config.json`: `model` (`auto` → a fixed Gemini model), `temperature`
      (0.5 → 0.8), `image_api_url`, `block_on_injection`.
- [x] **Hazard found and fixed:** combining live env overrides with the new
      save-every-field behaviour meant saving *any* Settings change would bake
      the env value into `config.json` permanently — silently replacing the
      `model: "auto"` (rotate Gemini/Qwen) choice made in the UI, and outliving
      the env var. `save_config` now excludes fields currently supplied by the
      environment. Verified live: after a real `PUT /api/config`, the file still
      reads `"auto"` while the runtime uses the env value.
- **Decision for the CEO:** `.env` still forces `STORYFORGE_MODEL` and
  `STORYFORGE_TEMPERATURE`. Those lines were written when overrides were inert,
  so they were never a deliberate choice. Remove them if the Settings UI should
  be authoritative.

### 3.4 Settings survive a restart (B2) — **VERIFIED LIVE**
- [x] Booted the server, issued a real `PUT /api/config` with CSRF, inspected
      `data/config.json`: **26/26 LLM fields and 217/219 pipeline fields** now on
      disk, up from 14 + 81 before. 24 `l2_*` fields persisted where there were
      none.
- [x] The two absent fields are intentional: `voice` (derived view) and
      `block_on_injection` (currently env-supplied, per §3.3).
- [x] `GET /api/config` reports `enable_pipeline_overlay: true` — it used to
      report `false` from a stale getattr default that contradicted
      `defaults.py`.

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
- [x] Unit-covered by `tests/test_resume_completeness.py` (7/20 chapters →
      incomplete; 20/20 → complete; continuation beyond the outline → complete).
- [ ] Live interrupt-and-resume against a real run — still worth doing once,
      alongside §3.1.

### 3.9 Server boot (added during the run) — **TWO REAL DEFECTS FOUND**
Not in the original plan; booting the app is what exposed them.
- [x] **Startup crash:** `.env` carries ~10 blank lines such as
      `WEB_CONCURRENCY=`. Loading it exported empty strings, and uvicorn does
      `int(os.environ["WEB_CONCURRENCY"])` — the server died before serving a
      request. `config/__init__` now skips blank values, so unset stays unset.
- [x] **`DATABASE_URL` guard confirmed working in anger:** the repo's own `.env`
      value is a sync sqlite URL. The log shows it caught, explained, and
      degraded to no-database instead of aborting startup — exactly the case B1
      predicted.
- [x] Clean boot verified after both fixes.

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
| Full-suite gate | PASS | 4883 passed, 0 failed, 6 skipped; EXIT1/2/3/5 = 0 |
| Combined coverage | PASS | 74%, up from the 70% baseline |
| §3.1 craft lane | PASS | integration test + causal proof |
| §3.2 secrets at rest | ACTION NEEDED | placeholder key found; migration reverted, product hardened |
| §3.3 env overrides | PASS | leak-into-file hazard found and fixed |
| §3.4 settings persistence | PASS | verified live: 243 fields on disk, was 95 |
| §3.9 server boot | PASS | after fixing two defects found during the run |
| §3.5-3.7 browser/visual | NOT RUN | need a browser session and a real image provider |
