# StoryForge Engineering Loop — Worklog

## Cycle #6 — RAG batch-cache test pollution + dormant mutmut gating (2026-06-11)

- **Task ID**: cycle6-rag-multi-query + cycle6-mutation-smoke
- **Agent**: Claude (eng-loop, autonomous)
- **Task**: Fix the two 2-failure clusters (4 of the 14 failures recorded in cycle #5).

### Work Log

1. **test_rag_multi_query (2F, order-dependent)** — `RAGBatchCache` is a process-wide singleton keyed on (summary[:200], sorted char names, thread ids). Several tests in the file reuse the same outline summary + character "Linh", so the second test with a colliding key got the first test's cached block back and `build_rag_context` returned before touching the fake KB (`"near" not found`, `StopIteration` on `kb.calls`). Autouse `_fresh_rag_batch_cache` fixture now calls `reset_batch()` per test. The cache-hit branch lost its (accidental) coverage, so a new `test_batch_cache_short_circuits_repeat_query` covers it deliberately — first detected as a −0.01pp coverage dip in run #13, recovered in run #14.
2. **test_mutation_smoke (2F)** — mutation-testing infra is dormant: `mutmut_config.py` was created in 6b6e505 and removed as a dead file in 0c4fede, and mutmut was never in any requirements file. The two environment-asserting smoke tests (`mutmut --version` exits 0; config file exists) now carry `skipif(find_spec("mutmut") is None)` — they gate only environments where mutation CI is actually provisioned, instead of failing every unprovisioned checkout. The module-importability and how-to tests still run everywhere.

### Stage Summary (verification gate)

- Full suite run #14: **10 failed, 4384 passed, 6 skipped, 0 errors** in 214s — exactly the 4 fixed, zero regressions (FAILED set identical to run #13 minus the 4).
- Coverage **69.59%** (= baseline 69.59%) ✓. Circular-import smoke ✓. Ruff clean on both touched files. Test-only changes (commit `51691a1`).
- Probe finding for next cycle: `test_scene_enhancer::test_defaults_are_set` passes alone AND with its own file → polluter is in another file (likely shared root cause with several remaining singles).

### Backlog (remaining 10 failures, next cycles)

- Singles, several confirmed order-dependent: scene_enhancer (cross-file pollution, bisect needed), voice_contract, chapter_contract, chapter_contracts, consistency_engine, error_paths, foreshadowing_verifier, outline_metrics, pipeline_core_coverage, perf/sprint2_10ch_bench

## Cycle #5 — Three 3-failure clusters: schema drift, async orchestrator, singleton mock poisoning (2026-06-11)

- **Task ID**: cycle5-pipeline-coverage + cycle5-integration-pipeline + cycle5-layer2-upgrade
- **Agent**: Claude (eng-loop, autonomous)
- **Task**: Fix the three 3-failure clusters (9 of the 23 failures recorded in cycle #4).

### Work Log

1. **test_pipeline_coverage (3F)** — two drifts: (a) `PlotThread` now requires `thread_id` + `planted_chapter` (no `started_chapter`; `status` defaults to "open") — test constructs with the new fields; (b) `pipeline.layer3_video` was removed in the image-focus pivot, so `patch("pipeline.layer3_video.storyboard.LLMClient")` raised AttributeError in both orchestrator-init tests — patch line dropped.
2. **test_integration_pipeline (3F)** — `run_full_pipeline` became async; sync callers got a coroutine (`'coroutine' object has no attribute 'status'`). All 4 call sites wrapped in `asyncio.run(...)` — this also un-vacuated `test_enable_media_defaults_false`, which "passed" without ever awaiting the coroutine.
3. **test_layer2_upgrade (3F, order-dependent)** — the deep one. `LLMClient` is a process-wide singleton; `monkeypatch.setattr(instance, "generate_json", fake)` records the restore value via `getattr`, which returns the **bound method from the class** — so the undo writes that bound method into the singleton's `__dict__`, permanently shadowing every later class-level `@patch(...LLMClient.generate_json)` → real LLM calls → swallowed connection errors → `_find_weak_chapters` returns empty → `assert 0 > 0`. Bisected the polluter to test_image_prompt_gen (probe test confirmed the instance-dict shadow). Fix: replace `gen.llm`/`extractor.llm` wholesale with `types.SimpleNamespace` stubs (5 sites in test_image_prompt_gen, 3 in test_shot_list) + standing autouse conftest guard `_unshadow_llm_singleton` that strips leaked method shadows after each test.

### Stage Summary (verification gate)

- Full suite run #12: **14 failed, 4381 passed, 0 errors** in 199s — exactly the 9 fixed, zero regressions.
- Coverage **69.59%** (baseline 69.55%) ✓. Circular-import smoke ✓. Ruff on touched files: 8 findings, all verified pre-existing at HEAD via stash (E402 section-import style, F401, F841) — 0 new debt; my one new E402 (`import types` mid-file) was relocated to the top import block. Test-only changes (commit `c00c5a2`).

### Backlog (remaining 14 failures, next cycles)

- test_rag_multi_query (2), test_mutation_smoke (2)
- Singles: voice_contract, scene_enhancer, pipeline_core_coverage, outline_metrics, foreshadowing_verifier, error_paths, consistency_engine, chapter_contracts, chapter_contract, perf/sprint2_10ch_bench

## Cycle #4 — Three 4-failure clusters: quality routes, structural rewrite, long context (2026-06-11)

- **Task ID**: cycle4-quality-routes + cycle4-structural-rewrite + cycle4-long-context
- **Agent**: Claude (eng-loop, autonomous)
- **Task**: Fix the three remaining 4-failure clusters (12 of the 35 failures recorded in cycle #3).

### Work Log

1. **test_quality_routes (4F)** — `_CHECKPOINT_DIR` removed from `api.quality_routes`; the `/quality` batch summary now scans `pipeline.orchestrator_checkpoint._all_checkpoint_dirs()`. Tests patch `orchestrator_checkpoint.CHECKPOINT_DIR` instead — by design that redirects the entire per-story + legacy scan (its parent becomes the scan root).
2. **test_structural_rewrite_parallel (4F)** — `_run_structural_rewrites` gained a duplicate-rewrite guard (`assert ch_num not in self.enhancer._rewritten_chapters`); the test's SimpleNamespace stub lacked `enhancer`, so every chapter raised AttributeError *before* the try block and `gather` swallowed it → 0 rewritten, 0 failed. Stub now carries `enhancer=SimpleNamespace(_rewritten_chapters=set())`.
3. **test_long_context (4F)** — two causes. (a) `estimate_tokens` prefers tiktoken (exact BPE: 400×"a" merges to 45 tokens) over the heuristic the tests asserted; tests pin `_TIKTOKEN_AVAILABLE=False` and assert the current 4.0 chars/token Latin ratio (single char now `max(1, …)` = 1, not 0). (b) LC integration test: chapters generate in parallel batches and siblings only see chapter texts frozen from *prior* batches, so with the default batch size chapter 2 saw no prior text and never took the long-context path; test sets `chapter_batch_size=1`. ("All LLM providers failed" log lines were noise, not the cause.)

### Stage Summary (verification gate)

- Full suite run #11: **23 failed, 4372 passed, 0 errors** in 188s — exactly the 12 fixed, zero regressions.
- Coverage **69.55%** (baseline 69.38%) ✓. Ruff check clean on touched files (1 unused import auto-fixed). Test-only changes.

### Backlog (remaining 23 failures, next cycles)

- test_pipeline_coverage (3), test_layer2_upgrade (3), test_integration_pipeline (3)
- test_rag_multi_query (2), test_mutation_smoke (2)
- Singles: voice_contract, scene_enhancer, pipeline_core_coverage, outline_metrics, foreshadowing_verifier, error_paths, consistency_engine, chapter_contracts, chapter_contract, perf/sprint2_10ch_bench

## Cycle #3 — Injection corpus contract + test-connection mock (2026-06-11)

- **Task ID**: cycle3-injection-corpus + cycle3-test-connection
- **Agent**: Claude (eng-loop, autonomous)
- **Task**: Fix the largest remaining failure cluster (test_prompt_injection_corpus, 20F) plus the test_api_async::test_test_connection single.

### Work Log

1. **Injection corpus (20F)** — `sanitize_input()` changed contract: it now **raises** `InjectionBlockedError` on detection when blocking is enabled (default via `STORYFORGE_BLOCK_INJECTION`, read at import time); the corpus test still expected the legacy log-only `SanitizationResult` return. Test now treats the exception as "blocked" and a normal return as "allowed" — exercising the production default instead of patching blocking off. `InjectionBlockedError` also gained a `threats_found` attribute (backward-compatible; existing catchers in `app.py` and `middleware/sanitization.py` are unaffected) so callers can report what triggered the block (commit `3901e7d`).
2. **test_test_connection (1F)** — `/api/config/test-connection` gained a per-profile `check_provider` fanout; the test only mocked `check_connection`, so unpacking the MagicMock default return raised `ValueError` at `api/config_routes.py:407`. One-line mock added (commit `e2cf6c5`).

### Stage Summary (verification gate)

- Full suite run #10: **35 failed, 4360 passed, 0 errors** in 196s — exactly the 20F+1F fixed, zero regressions.
- Coverage **69.38%** (baseline 69.35%) ✓. Ruff check clean on all 3 touched files; 2 were already in the pre-existing 457-file `ruff format` backlog (verified at HEAD via stash — no new debt).
- Sanitizer blast radius checked: all 63 `-k "sanitiz or injection"` tests green.

### Backlog (remaining 35 failures, next cycles)

- test_structural_rewrite_parallel (4), test_quality_routes (4), test_long_context (4 — unmocked LLM calls)
- test_pipeline_coverage (3), test_layer2_upgrade (3), test_integration_pipeline (3)
- test_rag_multi_query (2), test_mutation_smoke (2)
- Singles: voice_contract, scene_enhancer, pipeline_core_coverage, outline_metrics, foreshadowing_verifier, error_paths, consistency_engine, chapter_contracts, chapter_contract, perf/sprint2_10ch_bench

## Cycle #2 — Triage failure clusters: sidecars + SQLAlchemy reprs (2026-06-11)

- **Task ID**: cycle2-sidecar-isolation + cycle2-db-model-reprs
- **Agent**: Claude (eng-loop, autonomous)
- **Task**: Fix the three largest pre-existing failure clusters (26 failures + 3 errors of the 79F/3E recorded in cycle #1).

### Work Log

1. **SQLAlchemy repr tests (8F)** — `Model.__new__(Model)` bypasses the instrumented `__init__`, so attribute writes fail on SQLAlchemy 2.0.44 (`'NoneType' object has no attribute 'set'`). Switched to declarative constructors; `test_models_share_base` had a broken MRO-gymnastics assert (`Table` isinstance `type`) — now asserts `sqlalchemy.Table` (commit `0bd8166`).
2. **usage_history (9F) + continuation_history (6F+3E)** — sidecars moved to per-story folders (`output_paths.checkpoints_dir(title)` for writes, `find_checkpoint_path` for reads) but tests only patched the legacy `checkpoint_dir()` fallback → writes landed in the real `output/` tree while reads looked in tmp_path. Autouse fixtures now patch all three resolution seams. The `client` fixture also patched `continuation_routes._CHECKPOINT_DIR`, which no longer exists → AttributeError errored all 3 endpoint tests; removed (commit `f31cd61`).

### Stage Summary (verification gate)

- Full suite run #9: **56 failed, 4339 passed, 0 errors** in 187s — exactly the 26F+3E fixed, zero regressions.
- Coverage **69.35%** (baseline 69.27%) ✓. Ruff on touched files: clean. Test-only changes, no architecture impact.

### Backlog (remaining 56 failures, next cycles)

- test_prompt_injection_corpus (20) — biggest cluster, likely shared root cause
- test_structural_rewrite_parallel (4), test_quality_routes (4), test_long_context (4) — long_context shows live "All LLM providers failed" errors → unmocked LLM calls
- test_pipeline_coverage (3), test_layer2_upgrade (3), test_integration_pipeline (3), test_rag_multi_query (2), test_mutation_smoke (2)
- Singles: voice_contract, scene_enhancer, pipeline_core_coverage, outline_metrics, foreshadowing_verifier, error_paths, consistency_engine, chapter_contracts, chapter_contract, api_async (test_test_connection), perf/sprint2_10ch_bench

## Cycle #1 — Suite completes without hanging + zero F821 (2026-06-11)

- **Task ID**: cycle1-suite-hang + cycle1-f821
- **Agent**: Claude (eng-loop, autonomous)
- **Task**: The full pytest suite hung indefinitely on Windows (never completed once); repo had F821 undefined-name errors.

### Work Log

Six stacked hang causes found and fixed, each independently verified:

1. **Unmocked validator LLM calls** — validators added after tests were written made real LLM calls in `test_enhancer_async_guard`; stubbed.
2. **FlowKit refine before WS check** — `image_generator.py` called an LLM refine round-trip before checking `active_ws`; guard added (commit `278b2ad`).
3. **Dev config leaking into tests** — `comic_shot_list_enabled` from gitignored `data/config.json` changed test behavior; pinned off in `test_flowkit`.
4. **OpenAI SDK internal retries** — SDK 3 × client 3 × chain 3 ≈ 27 connection attempts per logical call; `max_retries=0, timeout=300` (commit `6a501a1`).
5. **Windows slow loopback refusal** — refused connects to closed ports take ~2-4s (dual-stack `localhost` ≈ 4.1s); conftest now rewrites every `*base_url` in the sandbox config to a local accept-and-close listener → failures in ~14-31ms (commit `ceb1506`).
6. **Cross-test config pollution** — `test_api_async.py:287` POSTs `base_url=http://localhost:8000/v1` through the settings API, mutating the ConfigManager **singleton** + sandbox file for every later test. Proven with a probe test; fixed with autouse `_restore_llm_config` snapshot/restore fixture (commit `ceb1506`).

Standing guards added: pytest-timeout 120s/test, pytest-socket (localhost-only), no-op retry-sleep seam, hermetic sandbox config.

F821: `chapter_contract.py` forward ref fixed via `TYPE_CHECKING` import (commit `0a9295a`); repo-wide `ruff check --select F821` now clean.

### Stage Summary (verification gate)

- Suite **completes**: 4313 passed, 79 failed, 3 errors, 4 skipped in 178s (was: never finished).
- Coverage **69.27%** (floor 60%) — recorded as baseline; no prior baseline existed because the suite never completed.
- Repo-wide F821: **0**. Ruff on touched files: 21 errors, **all verified pre-existing at HEAD** (E402/E702/F401/F841), 0 new.
- Circular-import smoke: pass. Targeted suites green: test_simulator, test_enhancer, test_flowkit, test_l2_signal_integration, test_pipeline_integration.
- 79 failures + 3 errors spot-checked at HEAD (stash test on test_usage_history, test_services_zero_coverage, test_continuation_history → identical failures) — **pre-existing, not regressions**.

### Backlog (next cycles)

- **P0**: Triage 79 pre-existing test failures + 3 errors. Clusters: test_prompt_injection_corpus (20), test_usage_history (9), test_services_zero_coverage SQLAlchemy reprs (8), test_continuation_history (6F+3E), test_structural_rewrite_parallel (4), test_quality_routes (4), test_long_context (4), test_api_async::test_test_connection ValueError (1), rest scattered. Full list: run `pytest -q` or see FAILED lines in any complete run log.
- **P1**: ~140 repo-wide ruff errors (79 auto-fixable); 457 files fail `ruff format --check`.
- **P1**: Oversized files (CONTRIBUTING 200-line rule), worst: `services/batch_generator.py` (1713 lines).
- **P2**: Proper LLM mocking for slow pipeline tests (some take ~30-60s against the dead listener due to attempt counts).
- **P2**: anthropic_provider / gemini_provider still use SDK-default retries (same multiplication risk as OpenAI had).
