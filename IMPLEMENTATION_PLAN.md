# Implementation Plan — StoryForge Upgrade Programme

Requirements doc: `docs/upgrade-plan-2026-08.md`. This file tracks execution.

**Not a greenfield build.** The product exists and runs. No stack selection, no scaffolding, no Docker bootstrap. Every task below modifies working code, so every task carries a regression test that fails before the fix.

Verified against source on 2026-08-22 before planning: `debate_mode` absent from `PipelineConfig` (confirmed), zero `load_dotenv` calls repo-wide (confirmed), `api_key` in `data/config.json` stored unencrypted (confirmed), **141 of 244 config fields never persisted** (11 LLM + 130 pipeline, measured).

---

## Sprint 1 — Phase 0: the 14 P0 defects

Grouped into 4 batches. Each batch is one reviewable unit of work on the sprint branch.

### Batch A — Resurrect the L2 craft lane (4 defects)

The headline finding: the craft-critique lane advertised as "13 specialized agents with debate" does not run at all in the default configuration, and the contract gate that guards output reports success without ever checking anything.

- [x] **A1. Restore the craft lane.** `pipeline/agents/agent_registry.py:243` reads `cfg.debate_mode`; the field does not exist on `PipelineConfig`, so the default path (`enable_agent_debate=True`, `config/defaults.py:289`) raises `AttributeError` the moment it reaches layer 2. It is swallowed at `pipeline/orchestrator_layers.py:1433-1435` into one `[AGENTS] WARN` line, `output.reviews` is never extended, and `SmartRevisionService` is starved of the reviews it revises from.
  - [x] Add `debate_mode: str = "full"` to `PipelineConfig` with the allowed values documented (`full` | `lite`).
  - [x] Regression test: run `run_review_cycle(layer=2)` against a default config and assert reviews come back non-empty — the test must fail on current `master`.
  - [x] Verify `api/pipeline_routes.py:767` (the only writer, sets `"lite"`) still behaves.
  - [x] Check the swallow site: an agent-panel failure must surface distinctly, not as an anonymous warning.

- [x] **A2. Make the post-L2 contract gate actually gate.** `pipeline/layer2_enhance/scene_enhancer.py:411-418` and `:470-477` rebuild `Chapter` without `contract` / `structured_summary`, so `contract_gate.py:296` sees `None` on every chapter, skips them all, and `enhancer.py:1607-1627` logs a false green "✅ Contract gate: 0 vi phạm".
  - [x] Carry `contract` and `structured_summary` through both `Chapter` reconstructions.
  - [x] Regression test: a chapter that violates its contract must be caught by the gate.
  - [x] Fix `_post_gate_validate` (`contract_gate.py:346`) reading `new_chapter.voice_contract` — an attribute assigned nowhere, so it always returns `True`. Read voice contracts from `sim_result.voice_contracts`.

- [x] **A3. Stop one late LLM failure from discarding the whole L2 layer.** `simulator.py:1171` (`evaluate_drama`) and `:1252` (`_generate_suggestions`) are unguarded; a failure on call ~91 propagates out of `run_simulation_async` to the layer-wide handler at `orchestrator_layers.py:1469-1487`, which throws away ~90 expensive successful calls and ships the raw L1 draft as `status="partial"`, `drama_score=0.0`.
  - [x] Guard both with degrade-in-place (fall back to the previous round's score / empty suggestions).
  - [x] Type-check `suggestions_result` before `.get()` (`simulator.py:1305, 1333-1334`).
  - [x] Emit a distinct SSE warning when L2 degrades, instead of silently shipping unenhanced prose.
  - [x] Regression test: inject a failure at the last round and assert the simulation result survives with prior rounds intact.

- [x] **A4. Distinguish a validation error from a validation failure.** `chapter_contract.py:169-181` and `:399-420` return `passed=False, compliance_score=0.0` when the *judge call itself* errors. `enhancer.py:536` / `:657` then trigger a full chapter re-enhance (~12-15 LLM calls) and `:699-733` reverts dialogue to the raw L1 text — all from one transient 429.
  - [x] Add an explicit `error` state distinct from `failed`.
  - [x] On `error`: skip remediation, record the incident, keep the enhanced chapter.
  - [x] Regression test: simulate a 429 on the validation call and assert no re-enhance and no dialogue revert.

### Batch B — Config integrity and secrets (3 defects)

- [x] **B1. Load `.env`; stop storing API keys in plaintext.** No `load_dotenv` exists anywhere in the backend (verified). Consequences: `STORYFORGE_SECRET_KEY` is unset so `services/secret_manager.py:34-40` returns `None` and secrets-at-rest encryption never runs — `data/config.json` currently holds an unencrypted `api_key`; all 30 `_ENV_MAP` overrides (`config/persistence.py:20-50`) are dead; `STORYFORGE_ALLOWED_ORIGINS`, `REDIS_URL`, `DATABASE_URL` never apply.
  - [x] Call `load_dotenv()` at the top of `app.py`, before config or logging is touched.
  - [x] Add `python-dotenv` to `requirements.txt` if absent.
  - [x] Migration path: on first boot with a key present, re-encrypt existing plaintext secrets in place and log the migration once.
  - [x] Guard the crash this unmasks: `services/infra/database.py:159` calls `create_async_engine` outside its `try`, so the repo's own `.env` value (`sqlite:///./data/storyforge.db`, a sync driver) makes startup raise. Either coerce to the async driver or fail soft with a clear message.
  - [x] Regression test: env override applies; a plaintext key is migrated to `ENC:`.

- [x] **B2. Persist the whole config, and stop deleting unknown keys.** `config/persistence.py:151-311` hand-lists fields: 141 of 244 are never written, so all 26 `l2_*` knobs, `enable_agent_debate`, `parallel_chapters_enabled`, `chapter_batch_size` and the budget caps silently revert to code defaults on restart. Worse, `save_config` rewrites the file wholesale, so any key present in `data/config.json` but missing from the writer is **deleted** on the next save (live example: `enable_consistency_rewrite`). Presets apply only partially for the same reason.
  - [x] Replace the hand-written dict with `dataclasses.asdict()` plus an explicit exclusion list for non-persistable fields.
  - [x] Preserve unknown keys already in the file rather than dropping them.
  - [x] Delete the ~60 dead `getattr(cfg, "x", default)` sites; 9 of them contradict `defaults.py` (`panels_max` 24 vs 12, `flowkit_aspect_ratio` 4:5 vs 9:16, `comic_shot_list_enabled` True vs False, `flowkit_veo_poll_interval` 5.0 vs 8.0, and 5 more).
  - [x] Regression test: round-trip every field through save→load; assert an unknown key survives a save.

- [x] **B3. Stop per-run flags from mutating global config.** `api/pipeline_routes.py:767-810` writes ~18 fields onto `orch.config.pipeline`, which is the process-wide `ConfigManager` singleton (`pipeline/orchestrator.py:86`). Two concurrent runs clobber each other, the mutation leaks into every later run in the process, and the next Settings save persists one run's ad-hoc flags. Separately, the toggle block at `:779-791` has no `else`, so it can only turn flags **on** — unchecking a box in the UI does nothing.
  - [x] Snapshot the flags a run overrides and restore them when it ends, so a finished run cannot dictate the next one or leak into the next Settings save.
  - [x] Make the toggles set the value, not just the truthy case.
  - [x] Regression test: the singleton is unchanged after a run; an unchecked flag is actually disabled.
  - [ ] **Deferred to Phase 1 — true concurrent isolation.** 26 modules read the `ConfigManager` singleton directly rather than `orch.config`, so overlapping runs with different flags remain last-writer-wins. Fixing that means a contextvar-scoped config (or threading config through those call sites), which is an architecture change, not a P0 patch.

### Batch C — User-facing data loss (2 defects)

- [x] **C1. Stop losing the user's library when localStorage fills.** `frontend/stores/library-store.ts:201-233` configures zustand `persist` with no error handling; the middleware writes *after* the in-memory state has already changed, so on `QuotaExceededError` the story looks saved, the success toast fires, and the whole library is gone on reload. A 50-story × 20-chapter prose blob passes the ~5 MB quota long before the 50-story cap. The throw also lands inside the SSE `onmessage` handler (`components/pipeline/PipelineScreen.tsx:159-167`), killing the stream mid-`done` so the panel just freezes.
  - [x] Catch persist failures and surface a real error state, never a success toast.
  - [ ] **Deferred to Phase 1** — move chapter prose to IndexedDB, keeping metadata in localStorage. The quota failure is now reported honestly instead of losing the library silently; raising the ceiling is a storage-layer change, not a P0 patch.
  - [x] Move `commitToLibrary` out of the SSE callback path so a storage error cannot kill the stream.
  - [x] Regression test: mock a quota throw; assert the user sees a failure and the existing library survives.

- [x] **C2. Reattach to a run after the stream drops.** Recovery polling is gated on `!pendingBody` (`components/pipeline/PipelineScreen.tsx:242`), but `pendingBody` clears only in `handleCancel` — so when the live stream errors the poller stays disabled and the user must reload the page by hand to rejoin a run the server is still executing.
  - [x] Clear `pendingBody` in `onError`/`onClose` so recovery engages automatically.
  - [x] Tell the backend when the user cancels; today `handleCancel` leaves `?session=` in the URL, so the poller resurrects the cancelled run and auto-saves it on `done`.
  - [ ] **Deferred to Phase 1** — suppress side effects during replay (a reload at chapter 12 still pops 12 toasts). Noisy, not destructive: `addStory` upserts by id, so the re-save is idempotent.
  - [x] Replace the permanent give-up after 5 consecutive errors (`useRunRecovery.ts:62,124-145`) with backoff — 7.5 s of backend trouble currently orphans a 20-minute run.
  - [ ] **Deferred to Phase 1** — extend recovery to the "Viết tiếp" flow, which has none. Needs the continue endpoints to expose a session id first.
  - [x] Regression tests for each of the five behaviours above.

### Batch D — Durability and correctness (5 defects)

- [ ] **D1. Make resume actually resume.** Per-chapter checkpoints are written but never read: `resume_from_chapter` (`orchestrator_checkpoint.py:278`) has no production call site and `resume_from_batch` (`batch_generator.py:112,163`) is never passed a non-zero value. `CheckpointManager.resume` (`:368-405`) sees a partial draft and runs L2 on it, so a crash at chapter 7 of 20 ships a 7-chapter story as complete. Checkpoint saves are fire-and-forget daemon threads (`:187-188`), so `await asyncio.to_thread(self.checkpoint.save, 1)` awaits only the thread spawn, not the write.
  - [ ] Wire `resume_from_batch` into the resume path.
  - [ ] Compare `len(chapters)` against `len(outlines)` before advancing to L2; resume L1 when short.
  - [ ] Await the real write at layer boundaries so a SIGTERM cannot truncate it.
  - [ ] Regression test: kill mid-run, resume, assert all chapters are generated.

- [ ] **D2. Fix the LLM cache key.** `services/llm/client.py:747` reads with the *configured* model while `:834-835` writes with the model that actually answered, so the cache almost never hits after any fallback — and because `generate_for_layer` delegates to `generate(model=...)`, layer 2 can be served a cached layer 1 answer. `max_tokens` is absent from the key, so a truncated 512-token answer is replayed for an 8192-token request.
  - [ ] Key on the resolved model plus `max_tokens`; namespace by layer.
  - [ ] Regression test: a layer-2 call must never receive a layer-1 cached body.
  - [ ] Note for Phase 1: caching is currently on up to `temperature <= 1.0`, which replays identical text into quality-gate retries so they cannot converge. Fix belongs with the cost work.

- [ ] **D3. Finish the request-timeout rollout.** `providers/anthropic_provider.py:19` and `providers/gemini_provider.py:16` ignore `llm.request_timeout` and keep their SDKs' internal retries, re-creating the retry multiplication the OpenAI provider's comment says it avoids. The stream wrapper kills at `stream_first_chunk_timeout=180` — exactly the slow case the 900 s default was raised for — and `fallback_max_latency_ms=120000` will blacklist legitimately slow models.
  - [ ] Pass `timeout` and `max_retries=0` to both providers.
  - [ ] Derive the stream and latency thresholds from `request_timeout` instead of fixing them independently.
  - [ ] Regression test: all provider paths honour a configured timeout.

- [ ] **D4. Stop one failed panel from corrupting every later comic page.** `services/media/image_generator.py:217-225` appends only successful paths, shortening the list, while `page_compositor.py:1070-1078` slices it positionally per page — so one failure shifts every subsequent panel into the wrong cell and speech balloons land on the wrong art.
  - [ ] Append a `None` sentinel on failure; `_place_panel` (`page_compositor.py:469-487`) already draws a placeholder.
  - [ ] Report partial chapters instead of silently returning `[]` (`comic_chapter.py:148-149`).
  - [ ] Regression test: fail panel 3 of 8, assert panels 4-8 stay in their correct cells.

- [ ] **D5. Let the FlowKit extension call back.** `POST /api/ext/callback` (`api/flowkit.py:109`) is not in the CSRF exemption list (`middleware/csrf.py:18-24`), so the extension — which has no CSRF cookie — gets 403 before its HMAC is ever checked.
  - [ ] Exempt the route; it is already authenticated by HMAC.
  - [ ] Regression test: a valid HMAC callback succeeds; an invalid one is still rejected.

### Sprint 1 exit criteria

- [ ] All 14 defects fixed, each with a regression test that fails on the pre-fix commit.
- [ ] `scripts/run_gate_chunks.ps1` clean, exit codes inspected by hand (the gate cannot fail on its own until Phase 3).
- [ ] `npx tsc --noEmit` clean; `npx vitest run` green.
- [ ] One PR to master from the sprint branch.

---

## Sprint 2-3 — Phase 1: LLM cost and wall-clock

Target: **−50% cost, −40% wall-clock** on a 10-chapter run (currently 450-700 calls, 1200+ when the quality gate retries). Measured before and after with real provider usage counts, which requires the token-accounting fix below to land first.

- [ ] Count tokens from provider responses instead of `len(text)//4`, which under-counts Vietnamese by ~45% and makes every budget cap meaningless.
- [ ] Bring the streaming path — the chapter body, the single largest consumer — into cost tracking and the wallet.
- [ ] Cache the voice engine process-wide (rebuilt per chapter and per retry today, ~50 redundant calls for identical output).
- [ ] Re-enhance only the failing scene on contract/voice retry, not the whole chapter pipeline.
- [ ] Remove the duplicate per-chapter scene decomposition on the sequential path.
- [ ] Replace whole-story regeneration on quality-gate failure with the existing targeted `SmartRevisionService`.
- [ ] Cap `generate_json` repair at one pass on the cheap tier (it stacks up to 4 full chain traversals today).
- [ ] Move the simulator's ~100 calls to the cheap tier where output is a scalar or filler; same for the 8-agent panel returning small JSON.
- [ ] Reorder the fallback chain: cheap model first in the cheap tier, primary model always present as last resort.
- [ ] Batch and parallelise the consistency engine (~100 strictly sequential cheap calls, one per character per chapter).
- [ ] Group the ~10 sequential validators in `finalize_chapter` into 2-3 gather groups.
- [ ] Parallelise the 6 independent L1 preamble calls (60-90 s of dead time at the start of every run).
- [ ] Parallelise comic panels within a chapter and chapters on the Reader path, so the FlowKit ramp can actually ramp.
- [ ] Collapse the 4-tier agent DAG to 2 tiers — only the editor consumes `prior_reviews`.
- [ ] Honour `max_parallel_workers`, which is currently read only to print a log line while the gather runs unbounded.
- [ ] Add a per-call deadline and bound the fallback chain length (3 retries × 50-300 entries × 3 passes today).
- [ ] Stop clearing the global 429 cooldowns between chain passes; parallel chapters currently destroy each other's rotation state.
- [ ] Disable cache reads on quality-retry paths so retries can converge.

---

## Sprint 3 — Phase 2: remove ~15,000 lines of dead code

Every item verified to have no caller. Runs alongside the tail of Phase 1.

- [ ] Dead DB layer (~1,100 lines): the database has zero rows in every table and nothing writes stories to it. Removes `_persist_*_to_db`, `diagnostics_routes`, `_load_story_from_db`, ORM models, alembic.
- [ ] 12 route modules no frontend calls (~2,500 lines), including `dashboard` which always 500s and `account_routes` which is never even mounted; plus 10 of 12 continuation endpoints.
- [ ] Veo/video remnants (~180 lines) including the SQLite poll loop that runs every 5 s from boot.
- [ ] Dead frontend (~1,400 lines) and the two unreachable reader routes — decide which reader route is canonical first, since one of them renders `ComicGenerator` against the prose-only Reader decision.
- [ ] Dead pipeline code (~800 lines): PROBE instrumentation shipping in production, `MediaProducer` never run, unread foreshadowing wiring.
- [ ] `plugins/`: `load_all()` is never called, so every hook on the hot path is a no-op. Wire it into startup or delete the hooks.
- [ ] `/api/v1` mirror: no client uses it; it doubles the route table and runs a middleware on every request.
- [ ] Consolidate duplicates (~2,000 lines): 5 copies of `_detect_provider_type`, 2 divergent pricing tables, 3 incompatible library-payload models, 5 near-identical SSE generators, 6 copies of the settings save handler, 3 route-local rate limiters.

---

## Sprint 4-5 — Phase 3: quality foundation

- [ ] Vietnamese golden dataset, 20 stories × 5 genres. The eval machinery already exists in `tests/benchmarks/` but its dataset is 20 **English** stories and its runner is not collectable.
- [ ] Make the gate able to fail: it passes `--cov-fail-under=0`, never aggregates exit codes, wastes 49 s on a chunk that collects zero tests, and carries ~1,900 phantom statements from deleted files. Real coverage is 70%.
- [ ] Typed SSE events alongside the human-readable log, so the UI stops deriving state from regexes over Vietnamese prose.
- [ ] One `ImageBackend` protocol for the 9 image providers; unified retry and fallback policy.
- [ ] Enforce the simulator/debate lane contract in code — the current filter cannot drop anything and two debate prompts instruct across the boundary.
- [ ] One shared `write_one_chapter()` across the sequential, parallel and continuation paths, which produce materially different quality today.

---

## Sprint 5 — Phase 4: packaging and docs

- [ ] Ship a UI in the production image; today the frontend is dockerignored and nothing serves it.
- [ ] Bake the spaCy model and MiniLM weights; run `alembic upgrade`; multi-stage build.
- [ ] Rewrite `AGENTS.md` / `ARCHITECTURE.md`, which currently instruct agents to run a command that crashes this host and describe deleted files, Alpine.js, Gradio and TTS.
- [ ] Fix or delete the broken scripts (deleted checkpoints, wrong UI port, hard-coded personal paths).
- [ ] Verify the static export against the 4 dynamic routes; stop shipping both locale catalogues to the client.

---

## Progress log

| Date | Phase | Status | Notes |
| --- | --- | --- | --- |
| 2026-08-22 | Batch C | Done | 2 defects fixed; quota no longer loses the library; dropped streams reattach; 9 new FE tests |
| 2026-08-22 | Batch B | Done | 3 defects fixed; config persistence 103 -> 244 of 245 fields; 41 new tests |
| 2026-08-22 | Batch A | Done | 4 defects fixed, 25 new regression tests, 367 L2/agent tests green |
| 2026-08-22 | Planning | Approved | Plan written from `docs/upgrade-plan-2026-08.md`; 4 headline P0 claims re-verified against source |
