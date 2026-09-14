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

- [x] **D1. Make resume actually resume.** Per-chapter checkpoints are written but never read: `resume_from_chapter` (`orchestrator_checkpoint.py:278`) has no production call site and `resume_from_batch` (`batch_generator.py:112,163`) is never passed a non-zero value. `CheckpointManager.resume` (`:368-405`) sees a partial draft and runs L2 on it, so a crash at chapter 7 of 20 ships a 7-chapter story as complete. Checkpoint saves are fire-and-forget daemon threads (`:187-188`), so `await asyncio.to_thread(self.checkpoint.save, 1)` awaits only the thread spawn, not the write.
  - [ ] **Deferred to Phase 1** — wire `resume_from_batch` so a partial L1 continues from the last completed batch. Resume now refuses to advance an incomplete draft into L2 (the data-loss half); restarting L1 from the last batch is a larger change to the batch generator's entry contract.
  - [x] Compare `len(chapters)` against `len(outlines)` before advancing to L2; resume L1 when short.
  - [x] Await the real write at layer boundaries so a SIGTERM cannot truncate it.
  - [x] Regression test: kill mid-run, resume, assert all chapters are generated.

- [x] **D2. Fix the LLM cache key.** `services/llm/client.py:747` reads with the *configured* model while `:834-835` writes with the model that actually answered, so the cache almost never hits after any fallback — and because `generate_for_layer` delegates to `generate(model=...)`, layer 2 can be served a cached layer 1 answer. `max_tokens` is absent from the key, so a truncated 512-token answer is replayed for an 8192-token request.
  - [x] Key on the resolved model plus `max_tokens`; namespace by layer.
  - [x] Regression test: a layer-2 call must never receive a layer-1 cached body.
  - [x] Note for Phase 1: caching is currently on up to `temperature <= 1.0`, which replays identical text into quality-gate retries so they cannot converge. Fix belongs with the cost work.

- [x] **D3. Finish the request-timeout rollout.** `providers/anthropic_provider.py:19` and `providers/gemini_provider.py:16` ignore `llm.request_timeout` and keep their SDKs' internal retries, re-creating the retry multiplication the OpenAI provider's comment says it avoids. The stream wrapper kills at `stream_first_chunk_timeout=180` — exactly the slow case the 900 s default was raised for — and `fallback_max_latency_ms=120000` will blacklist legitimately slow models.
  - [x] Pass `timeout` and `max_retries=0` to both providers.
  - [x] Derive the stream and latency thresholds from `request_timeout` instead of fixing them independently.
  - [x] Regression test: all provider paths honour a configured timeout.

- [x] **D4. Stop one failed panel from corrupting every later comic page.** `services/media/image_generator.py:217-225` appends only successful paths, shortening the list, while `page_compositor.py:1070-1078` slices it positionally per page — so one failure shifts every subsequent panel into the wrong cell and speech balloons land on the wrong art.
  - [x] Append a `None` sentinel on failure; `_place_panel` (`page_compositor.py:469-487`) already draws a placeholder.
  - [x] Report partial chapters instead of silently returning `[]` (`comic_chapter.py:148-149`).
  - [x] Regression test: fail panel 3 of 8, assert panels 4-8 stay in their correct cells.

- [x] **D5. Let the FlowKit extension call back.** `POST /api/ext/callback` (`api/flowkit.py:109`) is not in the CSRF exemption list (`middleware/csrf.py:18-24`), so the extension — which has no CSRF cookie — gets 403 before its HMAC is ever checked.
  - [x] Exempt the route; it is already authenticated by HMAC.
  - [x] Regression test: a valid HMAC callback succeeds; an invalid one is still rejected.

### Sprint 1 exit criteria

- [ ] All 14 defects fixed, each with a regression test that fails on the pre-fix commit.
- [ ] `scripts/run_gate_chunks.ps1` clean, exit codes inspected by hand (the gate cannot fail on its own until Phase 3).
- [ ] `npx tsc --noEmit` clean; `npx vitest run` green.
- [ ] One PR to master from the sprint branch.

---

## Sprint 2-3 — Phase 1: LLM cost and wall-clock

Target: **−50% cost, −40% wall-clock** on a 10-chapter run (currently 450-700 calls, 1200+ when the quality gate retries).

### Batch E — Measurement (done)

Nothing else in this sprint can be judged until spend is counted correctly.

- [x] Count tokens from provider responses instead of `len(text)//4`. Each provider now fills a per-call `usage_out` dict (no shared state between concurrent chapters); the estimator is used only as a fallback and now delegates to the Vietnamese-aware `token_counter` — measured 481 tokens where the old heuristic said 210 on the same sample, i.e. it ran 56% low.
- [x] Bring the streaming path — the chapter body, the single largest consumer — into cost tracking and the wallet. Streams accumulate their output and are costed on completion; a budget breach propagates, while a telemetry failure never costs the user their story.
### Batch F — Remove repeated work (in progress)

- [x] Memoise the voice engine per draft, under a lock. Five call sites rebuilt it once per chapter and again per retry — roughly 50 identical cheap calls on a 10-chapter, 5-character story. A failed build is remembered too, so it is not retried per call site.
- [x] Fix the same shape in `_theme_profile`: read-then-assign let concurrently enhanced chapters each start their own `extract_theme`.
- [x] Memoise scene decomposition per outline. Both the sequential write path and the enhancement-context builder decomposed the same chapter under the same flag. Uses a per-outline lock so callers for one chapter collapse into a single call while different chapters still decompose in parallel (measured: 4 chapters in 0.27s, not 1.0s).
- [x] Re-enhance only the failing scene on contract/voice retry, not the whole chapter pipeline. — **scoped down, with a reason.** `ContractValidation` carries no scene locator (missing escalations/subtext/causal refs are all chapter-level), so "the failing scene" is not derivable today; pinning one would be guesswork. What *was* pure waste is now gone: `enhance_chapter_by_scenes` splits and scores the chapter, and a chapter pipeline calls it four times (first pass, contract retry, voice retry, structural re-enhance) against text the retries did not change — each retry building a fresh `SceneEnhancer`, so no instance memo could help. A module-level cache keyed on the chapter text, with per-key locks, makes every run after the first cost nothing. `score_scenes` (one cheap call per scene) now runs concurrently too.
  - [ ] **Follow-up:** to actually target one scene, `ContractValidation` needs to localise each missing element to a scene — either a per-scene validation pass or a locator field on the judge's reply. Own change.
- [x] Replace whole-story regeneration on quality-gate failure with the existing targeted `SmartRevisionService`. — both gates (L1 and L2) now revise only the chapters they named, at the gate's own `chapter_threshold`, keeping a rewrite only when it re-scores better. The wholesale path stays as the fallback and that is deliberate: when every chapter clears the bar but the story scores low overall, the complaint is not localised and only regenerating the layer can move it. Note the old retry also accepted its replacement unseen — nothing compared it against what it replaced, so a worse second attempt shipped.
- [x] Cap `generate_json` repair at one pass on the cheap tier (it stacks up to 4 full chain traversals today). — one shared repair budget per `generate_json`, so the shape-mismatch retry no longer gets its own.
### Batch G — Model routing (done)

- [x] Route the simulator's low-stakes calls to the cheap tier: drama evaluation (read as a single score) and reaction posts (only ever seen truncated as recent-posts filler). Agent turns and escalation events stay on the primary model — those are the dramatic content itself. Reversible via `l2_cheap_low_stakes_calls`.
- [x] Cap the 8-agent panel's replies at `l2_agent_review_max_tokens` (1200). Each returns a small `{score, issues[], suggestions[]}` object and had no output cap, so it was billed against the model's full output budget. A source-level test keeps any new panel call from shipping uncapped.
- [x] Expose `l2_cheap_agent_panel`, **defaulted off**. Unlike the simulator's filler, the panel's critique is what SmartRevisionService rewrites from, so moving it to a weaker model is a quality decision for the CEO rather than an automatic saving.
- [x] Reorder the fallback chain: cheap model first in the cheap tier, primary model always present as last resort. — the `cheap_model_name is None` guard had excluded the primary from cheap-tier chains entirely.
### Batch H — Parallelism (in progress)

- [x] Parallelise character-state extraction: one cheap call per character per chapter, previously issued strictly one after another against the same excerpt. Prompt unchanged — this is a scheduling fix, so there is no quality risk. Results are merged on the calling thread and returned in a deterministic order rather than completion order.
- [ ] **Follow-up, needs measurement:** batch all characters into one call per chapter (~50 calls to ~10). Cuts cost as well, but changes the prompt and its parsed shape, so it needs a real story run to validate before shipping.
- [ ] Group the ~10 sequential validators in `finalize_chapter` into 2-3 gather groups.
- [x] Parallelise the 6 independent L1 preamble calls (60-90 s of dead time at the start of every run). — they are not 6 mutually independent calls: the real shape is two waves. Wave 1 {idea summary, premise, characters} reads only the raw request; wave 2 {voice profiles, world, arc waypoints} reads only the cast. Everything after (macro arcs -> outline -> critique) is a genuine dependency chain. Five sequential round-trips collapse to two barriers via `StoryGenerator._run_preamble_wave`.
  - Both wave-2 steps mutate the shared `characters` list, so the writes are applied on the calling thread after the wave joins, not inside the workers.
  - Each task runs under `contextvars.copy_context()`; without it, siblings sharing one context corrupt per-call token/cost attribution instead of failing.
- [x] `services/thread_pool_manager.py` has zero production call sites. **Decision: deleted** (with `_thread_pool_impl.py` and its test). Adopting it would not have helped: its `submit(pool_name, fn)` API cannot bound the total across several executors, which is exactly the image case, and LLM/CPU sites are already bounded by `max_parallel_workers`. A module nobody calls, whose caps bound nothing, only creates the appearance of control.
- [x] Parallelise comic panels **within a chapter**, so the FlowKit ramp can actually ramp. — `generate_story_images` now fans out over panels bounded by the new `pipeline.comic_panel_workers` (default 3; image endpoints rate-limit far harder than text ones). Results are written by index, never appended: completion order is not panel order and the compositor slices the list positionally.
- [x] Parallelise **chapters** on the Reader path. — `handle_generate_images` looped chapters one at a time while the pipeline media stage had been fanning the same shared `generate_chapter_comic` out all along. Paths are applied in chapter order, not completion order. Also fixed a real defect the tests exposed: one chapter raising used to hit the handler's outer `except` and return `[], "Error: ..."`, losing every other chapter's art.
- [x] **One ceiling for image work.** Chapter-level and panel-level fan-out multiply (4 x 3 = 12 requests in flight, not 4) and neither worker count bounds the other. New `pipeline.image_max_concurrent_requests` (default 4, 0 disables) is a process-wide semaphore held around the provider call itself — released across retry backoff, so a retrying panel does not sit on capacity. `pipeline.comic_chapter_workers` (default 4) now drives both entry points.
- [x] Collapse the agent DAG from 4 tiers to 2. Six of eight agents declared `depends_on` while ignoring the `prior_reviews` argument, so the panel ran in four sequential passes with nobody using the previous pass's data. Only the editor consumes it, so only the editor gets its own tier. A test now rejects a declared dependency that the agent does not actually read.
- [x] Honour `max_parallel_workers`. It was read only to print "parallel, N workers" while the gather dispatched every chapter at once — a 50-chapter continuation ran 50 chapter pipelines concurrently, each with its own nested pool.
### Batch J — Found by a real run, not by the suite

The CEO pointed out the local Gemini/Qwen proxy could be started and a real
story generated. It found a P0 in the first attempt that 5,000 tests did not.

- [x] **Layer 1 died outright whenever scene beats were produced.**
  `parallel_write_context.py:165` did `per_chapter_enhancement += scene_beats`,
  but `generate_scene_beats` returns `list[SceneBeat]` — `TypeError: can only
  concatenate str (not "list") to str`. The exception left `asyncio.gather` via
  `_run_batch_async`, so it was not one lost chapter: the whole layer failed
  with `status="error"` and zero chapters, *after* the entire preamble had been
  paid for (315 s, 41 calls on a 3-chapter run).
  - The module already ships `format_beats_for_prompt`, and the **sequential**
    write path has always used it. Only the parallel path — the default — did
    not. Same recurring shape as the rest of this sprint: two paths doing one
    job, one of them wired correctly.
  - Invisible to the suite because beats are gated on `pacing_type` and the
    generator returns `[]` on failure, so the `if scene_beats:` guard usually
    skipped the broken line. It only fires when beat generation *succeeds*.
  - Beat generation is now non-fatal like every other prompt enrichment beside
    it; a flaky cheap call must not cost the whole story.
- [ ] **Follow-up:** the real run is the only thing that caught this. Add a
  smoke run against the local proxy to the release checklist — the gate cannot
  substitute for it.
- [x] **P0 — 5 chapters requested, 2 written, reported "Layer 1 hoàn tất".**
  Found by the Batch K smoke run on 2026-09-14. The legacy run of the same idea
  kept all 5, so this is not the repair loop. Chain, from `repair_on.log`:
  1. `revise_outline_from_critique` got 18,871 completion tokens back (558 s).
     The JSON contained a raw newline inside a string (`Invalid control character`).
  2. `_repair_json` does not handle that, so `generate_json` sent the fixer
     `text[:4000]` (`generation.py:175`) — the head of a much longer response.
  3. `gemini-3.1-flash-lite` returned valid JSON holding **2** chapters.
  4. `outline_critic.py:557` only rejects an *empty* revision, so the 2-chapter
     outline replaced the 5-chapter one.

  Nothing after that point noticed: batching, writing, the foreshadowing plan
  (payoffs planned for ch4–5, completion 0%), and the "done" message.
  - Fix at the root, two guards:
    - `revise_outline_from_critique` keeps the originals unless
      `len(revised) == len(outlines)`.
    - `generate_json` tries `json.loads(text, strict=False)` before any repair,
      and never sends the fixer a truncated text. This fix is shared with
      Batch L L2a — one change, not two.
  - Regression tests, each failing on `master`:
    - `test_revised_outline_with_fewer_chapters_is_rejected`
    - `test_raw_newline_in_string_parses_without_llm`
    - `test_json_fixer_never_receives_truncated_text`
  - Worth a guard at the layer boundary too: L1 should warn loudly when
    `len(draft.chapters) < num_chapters`.
  - **2026-09-14: both guards implemented** on `sprint/entity-and-shotlist`
    (CEO approved). `tests/test_outline_shrink_and_json_fixer.py`: 5 of 8 tests
    fail on `master`; the other 3 lock that a full revision and a short
    malformed repair still work.
    - One pre-existing test changed because it encoded the defect:
      `test_outline_critic_fidelity.py::test_literal_mode_triggers_reroll_when_coverage_below_floor`
      fed a 2-chapter outline and accepted a 1-chapter revision. Its payload now
      holds 2 chapters.
    - Full gate green: 5,135 passed, 0 failed.
- [x] **All 10 L2 agent prompts ran without Vietnamese diacritics.** Found by
  the CEO on 2026-09-14 ("các prompt đang mất dấu").
  - **Cause:** `agent_prompts._get_prompt` prefers the shipped
    `data/prompts/agent_prompts.yaml` over the built-in `_DEFAULTS`. That YAML
    has had the stripped text since it was created:
    - Created accent-stripped when the prompts were externalized (`59ebffa`).
    - Only partly restored by `33348e4` ("Vietnamese diacritics").
    - 287 accented characters, against 1,482 in the defaults.
    - Ignoring accents, the text is identical to the defaults.

    So all 8 review agents and both debate agents received
    "Ban la Chuyen Gia Nhan Vat … Tra ve JSON theo dinh dang sau".
  - **Scan:** every string literal in backend Python (AST) and every prompt data
    file, 342 files. The YAML is the only affected prompt source. One
    user-facing log line was also stripped (`simulator.py:1396`). The one
    "mojibake" hit (`eval_pipeline.py:23`) is a diacritic-detecting regex,
    not a defect.
  - **Fix:**
    - YAML regenerated from `_DEFAULTS` (verified key by key after parsing).
      Comments kept; `_meta` bumped to 1.1.0 with a changelog entry.
    - Log line restored.
  - **Tests:** `tests/test_agent_prompts_diacritics.py`, 20 of 22 failing on
    the old YAML.
    - The shipped YAML must match the defaults, so the two copies cannot drift
      again.
    - The prompt each agent actually receives must carry no unaccented
      Vietnamese word.
  - Full gate green: 5,135 passed, 0 failed.

### Batch I — Retry discipline (done)

- [x] Cap auto-discovered round-robin models at `max_discovered_models_per_key` (3). Explicitly configured `fallback_models` are untouched — capping the whole chain would have dropped exactly the fallbacks the operator chose on purpose.
- [x] Add `max_total_call_seconds` (1800, 0 disables): an absolute ceiling on one `generate()` across its chain, per-entry retries and backoff sleeps.
- [x] Stop clearing the global 429 cooldowns between chain passes. Only expired entries are dropped now, and the all-keys-cooling release valve retries without erasing state other threads are still routing by.
- [x] Disable cache reads on quality-retry paths so retries can converge. — `no_cache_reads()` ContextVar, applied to both L1 contract-retry rewrites. Writes stay on.

---


### Batch K — Repair loop cho L1 chapter finalize

Spec: `docs/agentic-repair-loop-spec.md`. Đây là khoản cost lớn nhất còn lại của
Phase 1 và cũng là một defect chất lượng: post-write của mỗi chương chạy 5 pass
sửa lỗi độc lập, worst-case **8 LLM call/chương trong đó 5 call sinh lại nguyên
chương** ở `max_tokens=8192` — với truyện 40 chương là ~200 lần viết lại nội dung
đã có. Cả 5 flag mặc định `True` (`config/defaults.py:374,388,442,447,460`).

Nguyên tắc bất di bất dịch (spec §1.3): **verifier là detector tất định, không
bao giờ là LLM-as-judge.** Vòng lặp dừng theo `count_words` /
`consistency_validators` / `verify_payoffs`, không theo điểm model tự chấm.

#### K-A. Hạ tầng — tách detect khỏi side-effect (không đổi hành vi)

- [x] Dựng `pipeline/layer1_story/repair/findings.py`: `Severity`, `RepairFinding`, `RepairPlan`, `RepairOutcome`.
- [x] Dựng `repair/collector.py`: gom finding từ 5 nguồn hiện có mà **không** mutate `story_context`. Hôm nay detector ghi thẳng vào `story_context.name_warnings` / `arc_drift_warnings` / `foreshadowing_payoff_missing` — phải tách detect khỏi commit-warning để chạy lại được trên bản candidate.
- [x] `find_referencing_symbols` (Serena) trên mọi symbol đụng tới trước khi sửa. `finalize_chapter` có 3 đường gọi (sync executor / async gather / serial fallback) — mọi rẽ nhánh phải đặt **bên trong** `finalize_chapter`, không ở callsite.
- [x] Regression test `test_collector_is_pure`: `collect_findings` không mutate `story_context`. Fail trước khi fix.
- [ ] Gate xanh với flag OFF. Không một byte hành vi nào đổi ở bước này.

#### K-B. Coordinator + executor, planner tất định (phần lớn giá trị nằm ở đây)

Chưa cần thêm LLM call nào: planner giả lập gộp mọi finding, `strategy` luôn
`full_rewrite`. Đủ để đóng bug ghi-đè và cắt 5 regen xuống 1.

- [x] 6 field config vào `config/defaults.py` (`enable_agentic_repair` — mặc định `True` theo K-D, `repair_max_rounds=2`, `repair_budget_calls=4`, `repair_regression_tolerance=0.0`, `repair_fallback_to_legacy=True`, `repair_min_severity="major"`). Không thêm `getattr(cfg, "x", default)` mới.
  - `repair_planner_model_tier` **chưa** thêm: planner hiện tất định, không gọi LLM. Field này thuộc K-C.
- [x] Env override `STORYFORGE_AGENTIC_REPAIR` vào `config/persistence.py` theo mẫu dòng 27.
- [x] `repair/executor.py`: một prompt rewrite mang **toàn bộ** `constraints` gộp từ mọi finding. Đây là fix cho bug (b) — hôm nay `EXPAND_CHAPTER` không hề biết payoff vừa được chèn.
- [x] Verifier + `repair/coordinator.py`: vòng lặp, budget cứng, rollback về baseline chụp trước vòng đầu, fallback về 4 lời gọi legacy khi hết budget mà còn lỗi.
  - Không có file `repair/verifier.py` riêng: verifier là `recheck_findings` trong `repair/collector.py`, dùng chung detector với bước collect.
- [x] Rẽ nhánh trong `chapter_finalizer.py:97-127`.
- [x] Tắt `chapter_critique_rollback` khi `enable_agentic_repair=True` (spec §10.1) — giữ `True` trên nhánh legacy.
- [x] Trace fields: `repair.rounds_used/calls_used/findings_before/findings_after/rolled_back/fallback_used/strategy`.
- [x] Regression tests, mỗi cái fail trước khi fix:
  - [x] `test_length_survives_payoff_fix` — chương 1800 từ + payoff thiếu, sau repair vẫn ≥ `length_gate_min_ratio × target` **và** payoff đã trả. **Đây là bug thật, reproduce được trên code hôm nay.**
  - [x] `test_repair_budget_hard_cap` — vượt `repair_budget_calls` thì thoát, không gọi thêm.
  - [x] `test_repair_rollback_on_regression` — findings tăng thì content về baseline.
  - [x] `test_repair_constraints_merged` — prompt chứa mọi `hard_constraint`.
  - [x] `test_repair_exception_non_fatal` — planner raise thì chương giữ nguyên, pipeline chạy tiếp.
  - [x] `test_repair_disabled_is_byte_identical` — flag OFF gọi đúng 4 hàm cũ, đúng thứ tự.
- [ ] Bật flag trên một truyện thử, ghi số `calls_used` vs legacy.
  - **Đổi so với spec, tìm ra nhờ test:** baseline score phải đo bằng **cùng
    thước đo** với candidate. Bản đầu chấm baseline từ warning tiền-tính trên
    `story_context` còn candidate thì chạy lại detector — hai thước đo khác nhau,
    nên một bản viết lại 1800→900 từ vẫn được chấm là "tốt hơn" và được nhận.
    `test_repair_rollback_on_regression` bắt đúng chỗ đó. Coordinator giờ chạy
    `recheck_findings` trên chính bản gốc để lấy baseline (miễn phí — mọi detector
    recheck được đều không dùng LLM).
  - Chỉ 4 nguồn `payoff/name/location/length` tham gia chấm điểm. `pacing` (tốn
    1 LLM call để đo), `arc` (`detect_arc_drift` đọc `character_states` chứ không
    đọc văn bản) và `critique` (LLM tự chấm) được mang theo làm ràng buộc nhưng
    **không** được chấm lại — chấm lại chúng là so đo mới với đo cũ.
  - Trace: hiện thực là `RepairStats` trong `services/trace_context.py` (cộng dồn
    cả run + vào `summary()`), thay vì 7 field rời — hợp style `RagEventStats` sẵn có.
  - `post_processing.py` stash `repair_prev_locations` / `repair_new_locations`:
    `character_locations` đã bị đẩy sang giá trị mới trước khi repair chạy, nên
    không stash thì không recheck được chuyển cảnh.

#### K-C. Planner thật (1 LLM call)

- [ ] `repair/planner.py`: chọn `targeted` / `full_rewrite` / `skip`, trả JSON hẹp.
- [ ] `test_planner_json_contract` — `strategy` ngoài 3 giá trị thì coi như `skip`, không crash.
- [ ] A/B 10 chương: so `calls_used`, `findings_after`, điểm critique cuối.

#### K-D. Quyết định default

- [x] **Bật mặc định — CEO quyết ngày 2026-08-26, sớm hơn cổng mà kế hoạch này đặt ra.**
  Kế hoạch ban đầu là chỉ bật sau khi K-C chứng minh call giảm ≥40% mà
  `findings_after` không tăng. Đánh đổi được chấp nhận có ý thức: đường repair có
  rollback theo detector tất định, có fallback về 4 pass legacy khi hết ngân sách,
  và mọi đường lỗi đều non-fatal — nên rủi ro tệ nhất là chất lượng kém đi ở một
  số chương, không phải hỏng pipeline.
- [ ] **Điều kiện bắt buộc phát sinh từ quyết định trên: smoke run thật trước khi merge.**
  Prompt hợp nhất (`repair/prompts.py`) tới giờ mới chỉ được kiểm bằng LLM giả.
  Gate không thay được việc này — cùng bài học đã ghi ở Batch J ("the real run is
  the only thing that caught this"). Cần một truyện ≥5 chương chạy thật, rồi đọc
  `trace.summary()["repair"]`: `calls_used` phải thấp rõ so với legacy,
  `findings_after_total` không được cao hơn `findings_before_total`, và
  `rollbacks` cao bất thường nghĩa là prompt đang sinh bản tệ hơn.
  - **2026-09-13: CEO quyết merge vào master qua PR #49 trước smoke run**, giữ flag bật.
    Điều kiện còn lại chỉ là gate xanh. Smoke run vẫn là việc phải làm — giờ là
    kiểm chứng sau merge, và nhánh dưới đây là đường lui nếu kết quả xấu.
  - **2026-09-14: đã chạy smoke run qua proxy Gemini-API (Qwen).** Cùng một ý tưởng, 5 chương × 1.500 từ, cache tắt.

    | | Repair bật | Legacy |
    | --- | --- | --- |
    | Chương viết ra | **2/5** (lỗi dàn ý P0 ở Batch J, đã sửa) | 5/5 |
    | Tổng call / thời gian | 95 call / 28 phút | 169 call / 71 phút |
    | Chi phí mỗi chương | $0,12–0,13 | $0,12–0,15 |
    | Viết lại sau khi viết chương | 5 call cho 2 chương: 3 vòng, 1 rollback, 1 lần fallback về legacy | 7 lần viết lại toàn chương cho 5 chương: pacing ở cả 5, consistency ở ch3 và ch4 |
    | Findings | 7 → 6 | không đo |

    **Chưa kết luận được.** Hai lượt không so được với nhau vì dàn ý khác nhau: lượt repair bị cắt còn 2 chương. Legacy cũng không có bộ đếm tương đương `repair_stats`. Tiêu chí "calls_used thấp rõ so với legacy" chưa được chứng minh, nhưng cũng chưa bị bác bỏ: không có rollback hàng loạt, và findings không tăng. Vì vậy **giữ flag bật**.
  - [ ] A/B đúng nghĩa:
    - Chạy L1 hai lần trên **cùng một checkpoint dàn ý**, dùng `resume_from_batch` hoặc nạp outline có sẵn.
    - Thêm bộ đếm call viết lại cho nhánh legacy, để so cùng thước đo.
    - Lỗi dàn ý P0 đã sửa, nên lần chạy này sẽ có đủ chương.
  - [ ] **Lỗi mới do chạy thật tìm ra:** chương 3 của lượt legacy dài 5.002 từ so với mục tiêu 1.500, gấp 3,3 lần. Length gate chỉ kéo dài chương khi `< length_gate_min_ratio × target`, không có trần trên. Cần đo tỉ lệ vượt trên nhiều truyện trước khi quyết có cần trần hay không.
- [ ] Nếu smoke run xấu: hạ `enable_agentic_repair` về `False` (một dòng, hoặc
  `STORYFORGE_AGENTIC_REPAIR=0`) — legacy vẫn nguyên vẹn và có test khoá.
- [x] **Sửa kill switch — nó vốn không tắt được gì.** `_apply_env_overrides` chỉ ép
  kiểu cho field nằm trong `_BOOL_FIELDS`; field bool thiếu ở đó nhận thẳng chuỗi,
  mà chuỗi rỗng thì bị `if not val: continue` bỏ qua còn chuỗi `"0"` là **truthy** —
  nên `FLAG=0` bật cờ lên. Dính hai cờ: `STORYFORGE_AGENTIC_REPAIR` (tôi vừa ghi
  vào docs là kill switch) và `STORYFORGE_LENGTH_GATE` (có sẵn từ trước, xưa nay
  chỉ bật được chứ không tắt được). Cùng họ với defect B3 "toggle chỉ bật được".
  `tests/test_env_bool_overrides.py` khoá cả hai, và có thêm một test khoá **quy tắc**:
  mọi field bool trong `_ENV_MAP` phải có mặt trong `_BOOL_FIELDS` — đó mới là thứ
  bắt được ca thứ ba, vì hai ca này đều lọt vào đúng theo cách đó.

### Batch L — Thực thể nhân vật và cắt phân cảnh (từ novelvids) — **chờ CEO duyệt**

Spec và lập luận: `docs/novelvids-adoption-plan.md`, vai trò như requirements doc
cho batch này. Bản đánh giá gốc đã được đối chiếu với code. Có ba chỗ lệch làm
đổi plan:
- Báo nhầm tên gọi đang đi vào finding được chấm điểm của Batch K.
- Đường mất panel thật là fixer nhận `text[:4000]`, không phải `_close_truncated_json`.
- Proxy Gemini-API luôn trả `finish_reason="stop"`.

#### L0. Đo nền (0 call LLM)
- [x] `scripts/measure_entity_gaps.py`: đo tỉ lệ báo nhầm tên, % chương dài hơn `CONTENT_WINDOW`, % panel có subject mà thiếu ảnh tham chiếu.
- [x] Ghi số liệu vào đây. Đo trên 5 truyện thật (8 văn bản, 24 chương), không tốn call LLM:
  - **Cảnh báo tên: cả 18/18 đều báo nhầm, không ca nào là alias hay viết sai thật.**
    - 13 ca do nhóm chữ viết hoa bị nối xuyên dấu câu (`"Ai?" Lâm Phong` → "Ai Lâm Phong").
    - 5 ca là từ đầu câu bị so khoảng cách chỉnh sửa với tên gọi ngắn ("Thân" ~ "Chân").
    - Mọi cảnh báo này đều là finding được chấm điểm trong repair loop Batch K.
  - **Nhân vật chỉ được gọi bằng một phần tên** (registry coi là vắng mặt): 1 cặp trên 24 chương. Truyện smoke thể loại hiện đại cũng nhắc tên đầy đủ ít nhất một lần mỗi chương.
  - **Chương dài hơn cửa sổ 8.000 ký tự:** 2/24 (8%), dưới ngưỡng 20%. Nhưng chương 1 của truyện smoke dài 11.892 ký tự, nên **sẽ đo lại trên truyện legacy 5 chương** trước khi quyết L2b/L2c.
    - **Đã đo lại (smoke run 2026-09-14, cấu hình hiện tại):** 4/7 chương dài hơn cửa sổ (57%, vượt ngưỡng 20%). Các chương dài 6.929–22.527 ký tự. Chương dài nhất thì hơn 14.000 ký tự không bao giờ được đưa vào shot list. Tỉ lệ 8% ở dữ liệu cũ là do chương cũ ngắn hơn. **Quyết định: làm L2b/L2c.**
  - **Panel có subject mà thiếu ảnh tham chiếu:** không đo được, vì shot list không được lưu ra đĩa.

#### L1'. Phạm vi mới theo số đo: sửa detector tên trước, alias sau
- [x] `validate_character_names` (`consistency_validators.py`) sửa 2 chỗ:
  - Chỉ nối chữ viết hoa qua khoảng trắng, không nối qua dấu câu hay xuống dòng.
  - Từ đơn ở đầu câu bị bỏ qua nếu dạng viết thường của nó cũng có trong văn bản. Tên viết sai ("Minnh") không bao giờ xuất hiện ở dạng viết thường, nên vẫn bị bắt.
  - Kết quả trên dữ liệu thật: **18 → 2**. Hai ca còn lại ("Khung cảnh…", "Ân tình…") là từ đầu câu không có dạng viết thường trong chương. Muốn loại nốt phải có từ điển, nên chấp nhận.
  - `tests/test_name_validator_false_positives.py`: 12 test lấy nguyên văn câu thật. 9 test fail trên `master`, 3 test khóa việc vẫn bắt được tên viết sai.
- [x] Gate xanh trên branch `sprint/entity-and-shotlist`: 5.135 test pass, 0 fail (2026-09-14).
- [ ] Bảng alias (các mục L1 bên dưới) **hoãn**. Số đo chưa cho thấy cần: không có ca alias nào, và registry chỉ bỏ sót 1 lần trong 24 chương. Mở lại khi có truyện cụ thể bị lỗi vì tên gọi.

#### L1. Alias nhân vật
- [ ] `Character.aliases: list[str] = []`, và `services/character_names.py` (`build_name_index`, `resolve_character`, `mentions`). Chỉ khớp chính xác, alias mơ hồ trả `None`.
- [ ] Tìm alias bằng cách ghép `aliases_used` vào prompt `EXTRACT_CHARACTER_STATE` có sẵn, không thêm call. Chỉ gộp khi chuỗi xuất hiện nguyên văn trong chương, không phải đại từ, và không trùng nhân vật khác.
- [ ] Thay 6 chỗ so khớp: registry `:66-69/:247/:307`, dialogue checker, `shot_list.py:438` (subject và speaker), `validate_character_names`, `consistency_validators.py:225`, và danh sách tên trong prompt viết chương. Mỗi chỗ chạy `find_referencing_symbols` trước.
- [ ] 8 regression test trong spec, kể cả `test_repair_loop_ignores_registered_alias`.

#### L2. Shot list không mất phần cuối chương
- [x] L2a: fixer của `generate_json` không nhận bản bị cắt (`len(text) > 4000` thì ném lỗi). Có test. Đã làm cùng lỗi P0 dàn ý (`5280bd5`).
- [x] L2b: cắt chương theo đoạn. Các chunk chạy tuần tự trong một chương và mang panel trước sang. Kiểm độ phủ theo từng chunk, `enforce_rules` chạy một lần.
- [x] L2c (gate: 5.146 test pass, 0 fail): phát hiện bị cắt cụt một cách tất định (parse lỗi và ngoặc chưa đóng) thì chia đôi và gọi lại, giới hạn độ sâu 3. Đường lùi về rỗng ở `:654` phải ghi lý do.
  - **Đổi so với spec:** không cần tự đếm ngoặc chưa đóng, và vẫn dùng `generate_json`, vì mọi test hiện có giả `generate_json`.
    - Từ L2a, `generate_json` đã ném lỗi khi response không parse được và dài quá 4000 ký tự. Lỗi đó giờ có kiểu riêng là `JSONTooLongToRepairError`, subclass của `ValueError`, nên mọi caller đang bắt `ValueError` vẫn chạy như cũ.
    - Shot list bắt đúng kiểu lỗi này thì chia đôi chunk ở ranh giới đoạn, không có thì ở ranh giới câu. Giới hạn là độ sâu 3 và chunk tối thiểu 800 ký tự.
    - Response bị cắt mà ngắn hơn 4000 ký tự vẫn đi qua fixer như trước. Khi đã cắt theo chunk, trường hợp này hiếm, vì `max_tokens` tăng theo số panel của từng chunk.
  - `tests/test_shot_list_chunking.py`: 8/11 fail trên code cũ. 3 test còn lại khóa hành vi cũ: chương ngắn vẫn gọi đúng 1 lần, lỗi không chia được thì lùi về rỗng, và không chunk nào vượt cửa sổ.
  - **Chạy thật qua proxy (2026-09-14)** trên chương 3 của smoke run legacy, dài 22.527 ký tự:
    - Chia thành 3 chunk (7.673 / 7.759 / 7.085 ký tự), 3 call, 58 giây. Chunk 2 và 3 đều có ghi chú TIẾP NỐI.
    - Ra 36 panel. Panel cuối ("Mùa nước nổi vẫn đang dâng cao…") khớp đoạn kết thật. Trước đây shot list chỉ thấy khoảng 1/3 đầu chương.
  - [x] **Quyết định sản phẩm: trần panel — CEO chọn A (giữ trần mềm), 2026-09-14.** Không đổi code: mọi beat giữ ảnh riêng, số ảnh tăng theo độ dài chương. Bối cảnh của quyết định: ra 36 panel dù `panels_max = 24`.
    - `_merge_to_budget` chỉ gộp các panel liền kề của **cùng** một beat và không bao giờ bỏ beat. Đây là thiết kế có chủ ý: vượt trần thì giữ nguyên, chỉ log.
    - Model cũng không theo mục tiêu số panel: được xin khoảng 4 mỗi chunk, trả về khoảng 12.
    - Trước L2, cửa sổ 8.000 ký tự vô tình giữ số panel thấp. Giờ số ảnh tăng theo độ dài chương, tốn thêm quota ảnh Qwen/ngày và thời gian.
    - Hai phương án:
      - **A:** giữ trần mềm. Đủ mọi beat, ảnh nhiều hơn.
      - **B:** trần cứng. Gộp các beat liền kề có `_beat_weight` thấp nhất, dồn thoại và caption vào panel còn lại, cho tới khi đạt `panels_max`. Vẫn phủ cả chương vì việc gộp rải khắp chương, nhưng mất ảnh cho beat nhỏ.
  - **Phát hiện L1, không phải lỗi L2:** panel #9–15 lặp một cảnh vì **chính văn bản chương** kể lại cảnh đó hai lần. Câu "Thôi được…" nằm ở vị trí 7.595 và 9.626; không có cửa sổ 200 ký tự nào trùng khít, tức cùng một cảnh được viết lại bằng lời khác. Khớp với việc chương dài 5.002 từ so với mục tiêu 1.500. Nghi các lượt viết lại hậu kỳ của legacy (pacing, consistency) chèn thêm thay vì thay thế. Cần kiểm trước khi quyết về trần độ dài.
- [ ] 7 regression test trong spec, kể cả test chương ngắn vẫn đúng 1 call.

#### L3. Hình thái nhân vật cho ảnh — B có đường lui A (CEO duyệt)

**Đổi thiết kế so với spec, CEO chọn ngày 2026-09-14: lưu ở profile store, không lưu trên `Character`.**
- Lý do: đường tạo comic từ Library gửi `_LibraryCharacterPayload`, chỉ có 4 field (`name`, `role`, `description`, `backstory`), còn `_payload_to_story_draft` bỏ mọi field khác. Muốn gắn `Character.forms` thì phải sửa 5 lớp: schema, type frontend, auto-save, payload, và hàm đổi sang draft. Truyện đã lưu từ trước vẫn không có hình thái.
- Cách làm mới: hình thái lưu trong `profile.json` của nhân vật, cạnh `frozen_prompt` và ảnh tham chiếu, rồi suy ra từ nội dung chương lúc tạo comic.
- Chi phí: thêm 1 call rẻ cho mỗi chương ở lần tạo comic đầu tiên, có cache theo nội dung chương. Điều này trái dòng "không thêm call" trong spec; CEO đã chấp nhận.

- [x] `services/media/character_forms.py`:
  - `detect_changes`: 1 call cheap. Chỉ nhận thay đổi khi tên khớp đúng một nhân vật và `evidence` là trích dẫn **nguyên văn** có trong chương.
  - `ensure_forms`: cache theo hash nội dung. Chương đổi nội dung thì quét lại và thay các form cũ của chương đó. Quét lỗi thì không đánh dấu, lần sau thử lại.
  - `for_chapter`: hàm thuần, chọn form có `from_chapter` lớn nhất mà không vượt N.
  - `prepare_form_references`: phương án B, sinh ảnh tham chiếu cho form một lần từ ảnh gốc qua provider trong `REF_CAPABLE`. Không làm được thì chỉ đổi prompt (phương án A).
- [x] `CharacterVisualProfileStore`: thêm `get_forms`, `add_form`, `remove_forms_from_chapter`, `set_form_reference`, và chỉ mục chương đã quét. `save_enhanced_profile` giữ nguyên `forms` khi dựng lại profile.
- [x] `handle_generate_images`: quét và chuẩn bị ảnh **tuần tự trước khi** chia chương chạy song song. Mỗi chương nhận `visual_profiles` và `character_references` của riêng mình. Hai đường comic đang dùng (theo session và Library job) đều đi qua đây. Toàn bộ bước này non-fatal.
- [x] Cờ `comic_character_forms_enabled = True` trong `config/defaults.py`.
- **Chạy thật qua proxy (2026-09-14)** trên checkpoint có sẵn:

  | Truyện | Lượt | Thời gian | Model đề xuất | Được nhận | Ghi chú |
  | --- | --- | --- | --- | --- | --- |
  | Tâm lý hiện đại, 5 chương | Prompt ban đầu | 5 call, 27s | 0 | 0 | Đúng: không nhân vật nào đổi ngoại hình. Lượt quét lại tốn 0 call (cache hoạt động) |
  | Tiên hiệp, 10 chương | Prompt ban đầu | 10 call, 47s | 5 | 5 | Cả 5 đều trích nguyên văn nhưng **không cái nào là ngoại hình để vẽ tiếp**: túi hương, áo bị gió xé rách, **"thân vỡ thành đống xương"**, **"đã chết"**, "áo tan thành hạt sáng" |
  | Tiên hiệp, 10 chương | Prompt chặt + chốt chặn cái chết | 10 call, 48s | 2 | 2 | "Mắt trong suốt, ánh kiếm quang" sau đột phá: hợp lý. "Túi hương đeo bên hông": sai, hại nhỏ |

  - Bài học: kiểm trích dẫn nguyên văn chỉ chặn được thay đổi bịa ra, **không** chặn được việc model hiểu sai "lâu dài". Nên sửa hai lớp:
    - Prompt: loại trừ chết, hủy thân, khoảnh khắc đang biến đổi, rách do giao chiến, phụ kiện cầm theo; `description` phải là ngoại hình kết quả.
    - Chốt tất định `_ENDS_THE_CHARACTER`: mô tả chứa dead/corpse/bones/shattered/… thì bỏ. Ca "đống xương" là ca có hại nặng nhất, vì nhân vật sẽ bị vẽ như vậy ở mọi panel sau, kể cả hồi tưởng.
  - **Giới hạn đã biết:** phụ kiện nhỏ (túi, ngọc bội) đôi khi vẫn lọt dù prompt đã loại. Không thêm chốt tất định theo từ khóa, vì "white robe with jade pendant" là thay đổi thật sẽ bị loại nhầm. Hại nhỏ: chỉ thêm một dòng mô tả phụ kiện vào prompt ảnh.
  - Giữ bật mặc định: truyện hiện đại không có báo nhầm, ca gây hại nặng đã bị chặn tất định, lỗi còn lại chỉ hại nhỏ.
- [x] `tests/test_character_forms.py`: fail toàn bộ trên code cũ vì module chưa tồn tại. Có thêm 4 test chặn ca cái chết, lấy nguyên văn từ lần chạy thật; 4 test này fail trước khi thêm chốt `_ENDS_THE_CHARACTER`. Có 1 test integration qua handler: chương 1 vẽ hình thái gốc, chương 2 và 3 vẽ hình thái mới.
- [x] Gate xanh: 5.166 test pass, 0 fail (2026-09-14).

#### L4. `appearances` (tùy chọn)
- [ ] Chỉ làm khi L0/L1 cho thấy `tiered_context_builder` promote sai ngữ cảnh.

---

## Sprint 3 — Phase 2: remove ~15,000 lines of dead code

Every item verified to have no caller. Runs alongside the tail of Phase 1.

- [ ] Dead DB layer (~1,100 lines): the database has zero rows in every table and nothing writes stories to it. Removes `_persist_*_to_db`, `diagnostics_routes`, `_load_story_from_db`, ORM models, alembic.
- [ ] 12 route modules no frontend calls (~2,500 lines), including `dashboard` which always 500s and `account_routes` which is never even mounted; plus 10 of 12 continuation endpoints.
- [x] Veo/video remnants removed — and it was wider than "~180 lines". Gone: `request_video`, `get_job`, `start_polling`/`stop_polling`, `_poll_jobs_loop`, `_poll_once`, **and the whole SQLite layer under them** (`_SCHEMA`, `flow_jobs`, `init_db`, `_db_execute`, `_db_query`, `_DB_PATH`) — `flow_jobs` only ever held Veo jobs; image generation is synchronous over the extension WebSocket and never touched it. `request_video` had **no production caller at all**, only a test, yet the poll task woke every `flowkit_veo_poll_interval` seconds for the lifetime of every process with FlowKit enabled — i.e. the image path everyone uses.
  - The config key reached further than the plan implied: `config/defaults.py`, three places in `api/config_routes.py`, the frontend Zod schema, **a visible number input in `FlowkitSettings.tsx`**, the `poll_running` status field and its TS type, and four docs. All removed together — a settings control for a loop that no longer exists is worse than the loop.
- [ ] Dead frontend (~1,400 lines) and the two unreachable reader routes — decide which reader route is canonical first, since one of them renders `ComicGenerator` against the prose-only Reader decision.
- [ ] Dead pipeline code (~800 lines): PROBE instrumentation shipping in production, `MediaProducer` never run, unread foreshadowing wiring.
- [x] `plugins/`: `load_all()` is never called. **Decision: wired in**, not deleted — the repo ships `plugins/README.md` and an example, so this is a documented extension point, and 11 hook call sites already exist on the hot path. One trap had to be closed first: `example-custom-genre.py` registers a genre *and* adds a bonus in `on_score`, so loading it at startup would have quietly changed every user's quality scores because the repo ships documentation. The loader now skips `example-*` / `example_*` by name; copy one to your own filename to enable it. Load failure is non-fatal — a broken third-party plugin must not stop the server booting.
- [x] `/api/v1` mirror deleted. It re-mounted nine routers under a second prefix and installed a `BaseHTTPMiddleware` — which wraps *every* request in an extra task and stream pair — purely to set a Deprecation header on paths no client called. Verified against the frontend: zero references. **Trap avoided:** `/api/v1/eval/*` is *not* from the mirror — `api/eval_routes.py` carries its own `/v1/eval` prefix, so those routes and their tests are untouched. `AGENTS.md` also described `api/v1/router.py` and a `build_v1_router()` factory that never existed; corrected.
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
| 2026-09-14 | Batch L | Planned — chờ CEO duyệt | Spec `docs/novelvids-adoption-plan.md`; L0 đo → L1 alias → L2 shot list (gộp mục 2+3) → L3 hình thái (chờ A/B) |
| 2026-09-13 | Batch K + Sprint 3 (một phần) | K-A/K-B done, merge qua PR #49 | Repair loop bật mặc định, smoke run thật còn nợ; K-C chưa làm. Sprint 3: bỏ Veo/jobs DB, xóa `/api/v1` mirror, nối plugins. Gate (flag ON): 5092 passed, 0 failed; FE tsc + 145 vitest xanh |
| 2026-08-26 | Batch K | Planned — chờ CEO duyệt | Spec `docs/agentic-repair-loop-spec.md`; 5 repair pass -> 1 vòng có ngân sách; verifier tất định (research §1.3) |
| 2026-08-22 | Batch D | Done | 5 defects fixed; 29 new tests; full gate pending |
| 2026-08-22 | Batch C | Done | 2 defects fixed; quota no longer loses the library; dropped streams reattach; 9 new FE tests |
| 2026-08-22 | Batch B | Done | 3 defects fixed; config persistence 103 -> 244 of 245 fields; 41 new tests |
| 2026-08-22 | Batch A | Done | 4 defects fixed, 25 new regression tests, 367 L2/agent tests green |
| 2026-08-22 | Planning | Approved | Plan written from `docs/upgrade-plan-2026-08.md`; 4 headline P0 claims re-verified against source |
