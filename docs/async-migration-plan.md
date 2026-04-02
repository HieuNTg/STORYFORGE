# Async Migration Plan — ThreadPoolExecutor Audit

**Sprint 14 · BE-2**
Audited: `pipeline/` and `services/` (grep: ThreadPoolExecutor, run_in_executor)

---

## 1. Call-Site Inventory

| # | File | Line | Function / Context | What it does |
|---|------|------|--------------------|--------------|
| 1 | `pipeline/agents/agent_registry.py` | 77 | `_run_tier_parallel` | Fans out agent `.review()` calls (LLM I/O) in parallel |
| 2 | `pipeline/layer1_story/generator.py` | 145 | chapter writing loop | Runs `_write_chapter_with_long_context` per outline (LLM I/O) |
| 3 | `pipeline/layer1_story/post_processing.py` | 29 | `post_process_chapters` | Post-processing per chapter (text transforms + optional LLM) |
| 4 | `pipeline/layer1_story/story_continuation.py` | 82 | `continue_story` | Writes continuation chapters in parallel (LLM I/O) |
| 5 | `pipeline/layer2_enhance/enhancer.py` | 129 | `enhance_all_chapters` | Parallelises `enhance_chapter` per chapter (LLM I/O) |
| 6 | `pipeline/layer2_enhance/simulator.py` | 198 | `_generate_reactions` | Fan-out character reactions (LLM I/O) |
| 7 | `pipeline/layer2_enhance/simulator.py` | 267 | `_run_round` | One debate round, all agents in parallel (LLM I/O) |
| 8 | `pipeline/layer3_video/storyboard.py` | 127 | `generate_character_prompts` | Per-character image prompt generation (LLM I/O) |
| 9 | `pipeline/layer3_video/storyboard.py` | 177 | `generate_full_script` | Storyboard generation per chapter (LLM I/O) |
| 10 | `pipeline/layer3_video/storyboard.py` | 202 | `generate_full_script` | Location + voice script (LLM + CPU) |
| 11 | `pipeline/layer3_video/_locations.py` | 48 | `generate_location_prompts` | Per-location prompt generation (LLM I/O) |
| 12 | `pipeline/orchestrator_media.py` | 102 | `run_media_pipeline` | Scene image generation (external image-gen API) |
| 13 | `services/quality_scorer.py` | 80 | `score_chapters` | Parallel chapter scoring (LLM I/O) |
| 14 | `services/tts/audio_generator.py` | 136 | `generate_book_audio` | Per-chapter TTS generation (external API I/O) |
| 15 | `services/tts/providers.py` | 28 | `_get_executor` | Shared executor for TTS provider calls (blocking SDK) |
| 16 | `services/_config_repo_json.py` | 150–162 | `get/set/get_all/delete` | `run_in_executor` wrapping synchronous file I/O |
| 17 | `services/_thread_pool_impl.py` | 35–83 | `ThreadPoolManager` | Named pool manager (infrastructure, not a call site) |

---

## 2. Classification

### Can migrate to `async` / `asyncio.gather`
These sites perform **I/O-bound** work (LLM API calls, HTTP requests).
Converting the underlying LLM client calls to `async` + replacing
`ThreadPoolExecutor` with `asyncio.gather` is safe and beneficial.

| # | Site | Notes |
|---|------|-------|
| 1 | `agent_registry.py:77` | LLM calls; convert `agent.review` to `async def` |
| 2 | `generator.py:145` | LLM chapter writes; convert chapter writer to async |
| 3 | `story_continuation.py:82` | LLM I/O only |
| 5 | `enhancer.py:129` | LLM I/O only |
| 6 | `simulator.py:198` | LLM reaction calls |
| 7 | `simulator.py:267` | LLM debate round |
| 8 | `storyboard.py:127` | LLM prompt gen |
| 9 | `storyboard.py:177` | LLM storyboard gen |
| 11 | `_locations.py:48` | LLM location prompts |
| 13 | `quality_scorer.py:80` | LLM scoring calls |
| 14 | `audio_generator.py:136` | External TTS API (async SDK available) |
| 16 | `_config_repo_json.py:150–162` | File I/O — can use `aiofiles` |

### Must stay threaded (CPU-bound or blocking library)
| # | Site | Reason |
|---|------|--------|
| 4 | `post_processing.py:29` | Text transforms may include heavy regex + CPU work |
| 10 | `storyboard.py:202` | Location gen is CPU-light but paired with `wave`/`ffmpeg` subprocess |
| 12 | `orchestrator_media.py:102` | Image generation SDK (`diffusers`) is CPU/GPU-bound |
| 15 | `tts/providers.py:28` | gTTS / pyttsx3 SDKs are synchronous; no async alternative |
| 17 | `_thread_pool_impl.py` | Pool infrastructure — keep as-is |

---

## 3. Migration Priority

**P1 — High impact, low risk (pure LLM I/O, self-contained)**
1. `agent_registry.py:77` — central fan-out, unblocks event loop during agent debates
2. `enhancer.py:129` — largest per-run cost (~N chapters × LLM call)
3. `quality_scorer.py:80` — called frequently after each run

**P2 — Medium impact, requires async client refactor**
4. `generator.py:145` — chapter writer needs async LLM client thread-through
5. `story_continuation.py:82` — same LLM client dependency
6. `simulator.py:198 + 267` — debate simulator (two sites, migrate together)

**P3 — Lower priority**
7. `storyboard.py:127 + 177` — Layer 3 is optional/less common
8. `_locations.py:48` — downstream of storyboard
9. `audio_generator.py:136` — TTS is opt-in
10. `_config_repo_json.py:150–162` — `aiofiles` drop-in, trivial but low value

---

## 4. Estimated Effort

| Priority | Sites | Effort | Prerequisite |
|----------|-------|--------|--------------|
| P1 | 3 sites | 2–3 days | LLM client already has async methods (check `base_agent`) |
| P2 | 4 sites | 4–5 days | Audit LLM client interface; propagate `async` up call chain |
| P3 | 4 sites | 3–4 days | `aiofiles` dep, TTS async SDK eval |
| **Total** | **11 async sites** | **~10 dev-days** | |

**Note:** Sites #4, 12, 15 (CPU-bound / blocking SDKs) should remain
`ThreadPoolExecutor`; wrap with `loop.run_in_executor` when called from async
context to avoid blocking the event loop.
