# Phase B — Async Background Comic Generation (Library stories)

**Status:** Proposal (sprint-ready) · **Date:** 2026-06-09
**Predecessor:** Phase A stopgap — shipped. Frontend chunks generation one chapter per
request (`LibraryComicGenerator.tsx → runChapters`), keeping each request under Node's
5-min proxy timeout. Phase A removed the bogus "Internal Server Error" but the tab must
stay open and active for the whole run.

> One-paragraph problem recap: comic generation for a multi-chapter Library story is
> minutes of work (each chapter ≈ `panels_per_chapter`, default 8, sequential FlowKit
> image calls). Phase A made it survive the proxy timeout by splitting into N requests,
> but the run is still tied to a live browser tab. Phase B moves the work into a
> server-side background job: POST returns `202 + job_id` immediately, the frontend
> polls and persists illustrated chapters to localStorage as they land. The run survives
> a tab close/reload and the user never babysits.

---

## 1. Product framing

### Problem & impact
- **Who:** anyone generating comics for a story longer than ~1–2 chapters — i.e. the
  *normal* case for a comic tool, not an edge case.
- **How often:** every long-story generation — the product's headline workflow.
- **Severity:** High. Phase A traded a crash for a babysitting tax + fragility ("don't
  touch your browser for 8 minutes"). The flagship action is still effectively unreliable
  for its most valuable use case.

### Goal
Server accepts the request, returns immediately, runs generation off the request thread.
Frontend polls for progress and persists each illustrated chapter to its localStorage
library *as it completes* — so the run survives a tab close/reload/refocus and the user is
never blocked.

### Non-goals (do not let these creep in)
- **No multi-device sync** — Library is localStorage on one browser.
- **No server-side story persistence** — server holds *transient* job state only; the
  frontend remains the owner of the finished comic.
- **No WebSocket/SSE push** if polling suffices — keep transport simple this sprint.
- **No multi-user queue / quotas / fairness** — single-process open-source build.
- **No hard durability across server restart** — we make restart *client-recoverable*,
  not invisible.
- **No redesign of the image pipeline** — Phase B changes *how generation is invoked and
  tracked*, not how a panel is drawn.

### User stories
1. **Generate without babysitting** — start generation and walk away (close tab, switch
   apps) without the run dying.
2. **See progress** — live "chapter X of N" so I trust it's working.
3. **Recover after reload** — reopen the story and resume showing progress / keep saving,
   without re-generating completed chapters.
4. **Regenerate one chapter** — fix one chapter's art without re-running the whole story.
5. **Handle "no provider configured"** — clear, actionable message *at start*, not a
   cryptic mid-run error.
6. **Trust the final state** — a story never spins "generating…" forever.

### Acceptance criteria (testable)
- **Long run completes:** N-chapter story → server returns a `job_id` in <~2s and
  generation continues server-side; no HTTP timeout regardless of run length.
- **Incremental save:** a chapter that finishes server-side is rendered + written to
  localStorage **before** the next chapter is awaited; reloading mid-run keeps completed
  chapters intact.
- **Recovery:** a job still running at reload → frontend re-attaches (via persisted
  `job_id`) and resumes polling/saving, no duplicate regeneration. *(Backend supports this
  on day one; the FE reattach UI may be deferred — see scope.)*
- **No provider:** no provider configured → clear message, **no job created, no bogus
  500**.
- **Mid-run provider failure:** failing chapter marked `error` with a readable reason; run
  **continues** with remaining chapters (partial value > all-or-nothing); job reaches a
  terminal state.
- **No stranded state:** any failure/restart → frontend resolves to a terminal/`interrupted`
  state with a Resume/Retry affordance within one poll interval; never an infinite spinner.

---

## 2. Technical design

Verified against current code via Serena: `api/image_routes.py` (the library route
`generate_library_images:241`, the `_in_flight` guard, `get_comic_status`, `_to_media_url`,
`_payload_to_story_draft`), `services/handlers.py:255` (`handle_generate_images`),
`frontend/lib/api/illustration.ts`, `frontend/components/library/LibraryComicGenerator.tsx`,
`frontend/stores/library-store.ts:103` (`setStoryChapterImages`), `frontend/lib/api/client.ts`.

### 2.1 Endpoint becomes async
**Decision: ONE whole-story job with per-chapter progress** (not N per-chapter jobs).
Phase A's chunking existed *only* to dodge the proxy timeout; once POST returns `202` in
ms, that constraint is gone. A single job reuses the in-process `_PayloadOrchWrapper` +
title-scoped `CharacterVisualProfileStore` across all chapters and preserves the existing
mode selection (`chapter=N` / `only_missing=true` / full-regen capped at
`MAX_CHAPTERS_PER_IMAGE_CALL`). The over-cap and empty-chapter **400s are raised
synchronously at submit** (before `202`), so the FE still gets them immediately.

Request body: **reuse `LibraryGenerateImagesRequest` unchanged** (`story`/`provider`/
`chapter`/`only_missing`) — no FE payload change.

`202` response model (new):
```python
class LibraryJobAcceptedResponse(BaseModel):
    job_id: str
    state: str                  # "queued" | "running" (if reattached)
    title: str                  # idempotency key
    total_chapters: int
    target_chapters: list[int]
    already_running: bool = False
```
Only this route's `response_model` changes (→ `LibraryJobAcceptedResponse`, `status_code=202`).
`GenerateImagesResponse` is **left intact** — it is shared by the checkpoint route
`generate_images` (verified via `find_referencing_symbols`), which is untouched.

### 2.2 Status / polling endpoint (new)
```
GET /api/images/library/jobs/{job_id}   -> LibraryJobStatusResponse   (404 if unknown/TTL-evicted)
```
Mirrors `ComicStatusResponse`/`ChapterComicStatus` plus job lifecycle:
```python
class LibraryJobChapterStatus(BaseModel):
    chapter_number: int
    title: str = ""
    has_images: bool = False
    image_count: int = 0
    image_urls: list[str] = []        # /media/... ready to render
    state: str = "pending"            # pending | running | done | error
    error: Optional[str] = None

class LibraryJobStatusResponse(BaseModel):
    job_id: str
    state: str                        # queued | running | done | error | cancelled
    title: str
    provider: str
    panels_per_chapter: int
    total_chapters: int
    chapters_done: int
    chapters: list[LibraryJobChapterStatus] = []
    chapter_images: dict[int, list[str]] = {}   # accretes; FE persists incrementally
    error: Optional[str] = None
    count: int = 0
    skipped_chapters: list[int] = []
```
`chapter_images` is the **same `dict[int, list[str]]` shape** `GenerateImagesResponse`
already returns, so the FE `persist()` / `setStoryChapterImages` path is byte-for-byte
compatible — no persistence change.

### 2.3 Job store
**In-process `dict` + `asyncio.Task`** — correct for a single-process open-source app; a
DB/Redis store is over-engineering. Generated panels are **already durable on disk** under
`OUTPUT_ROOT/<story-slug>/images` (served via `/media`), so the job record only holds
transient progress + the URL map. Losing it on restart costs a re-poll, not data.

```python
@dataclass
class _LibraryJob:
    job_id: str; title_key: str; state: str
    provider: str; panels_per_chapter: int
    target_numbers: list[int]
    chapters: dict[int, dict]          # ch -> {title,state,image_urls,error}
    chapter_images: dict[int, list[str]]
    skipped_chapters: list[int]; count: int; error: Optional[str]
    task: Optional[asyncio.Task]; cancel: bool
    created_at: float; finished_at: Optional[float]

_jobs: dict[str, _LibraryJob] = {}
_jobs_lock = asyncio.Lock()            # guards _jobs + _in_flight
_JOB_TTL_SECONDS = 30 * 60             # lazy-evict finished jobs
```
- **Submit:** under lock, dedupe (§2.4), create `state="queued"`, spawn
  `asyncio.create_task(_run_library_job(...))`, return `202`.
- **Run:** `state="running"`; per chapter → `await asyncio.to_thread(handle_generate_images,
  orch, provider, None, ch_num)` (same call as today) → map images through `_to_media_url`
  → write into `chapter_images`, mark chapter `done`, bump `count`. Per-chapter exception
  → mark that chapter `error`, **continue**. After loop → `done` (or `error` if all
  failed). Always `_in_flight.discard` in `finally`.
- **TTL:** lazy sweep on every submit + poll (no background timer); cap total jobs (~100).
- **Restart:** `_jobs` empty → poll returns `404` → FE re-derives state from
  `Story.chapters[i].images` (already in localStorage) and re-submits for still-missing
  chapters (idempotent via `only_missing`). Disk panels are not lost.

### 2.4 Concurrency & idempotency
Keep `_in_flight` but make the **job the source of truth** (fold updates under `_jobs_lock`).
Idempotency key = `library::{title}::{chapter}` (single) or `library::{title}` (whole).
- Identical-scope resubmit while a job is active → **return the existing `job_id` with
  `already_running=true` (200)**, not a blind 409 (friendlier; enables reattach-after-reload).
- Reserve **409** for an overlapping-but-different-scope collision (e.g. single-chapter
  request while a whole-story job covering it runs) — preserves the existing FE `comic_busy`
  toast path.
This also **fixes the stranded-`_in_flight`-on-disconnect bug**: the task is detached from
the request, so the `finally` clears the slot even if every client disconnects.

### 2.5 Cancellation & disconnect
The core fix: generation runs in a **detached `asyncio.Task`**, so client disconnect no
longer touches the job (the request already returned `202`). `asyncio.to_thread` workers
**cannot be force-killed**, so cancel is **cooperative at chapter boundaries**:
```
DELETE /api/images/library/jobs/{job_id}   -> sets job.cancel=True; worker breaks before next chapter
```
The in-flight chapter runs to completion (≈ minutes), partial results kept. Do **not** use
`task.cancel()` to stop the thread (orphans it). *(Cancel endpoint is optional for Phase B
— recommended, cheap, completes the disconnect-safety story.)*

### 2.6 Frontend integration
`LibraryComicGenerator.tsx` `runChapters` → `runJob`: submit once → poll → persist partials.
**Per-chapter incremental render is preserved** because polls deliver accreting
`chapter_images`.

New wrappers in `illustration.ts`: `submitLibraryComicJob(story, opts)`,
`getLibraryComicJob(jobId)`, `cancelLibraryComicJob(jobId)` (reuse `toLibraryImagePayload`).
Delete the now-dead `generateLibraryMissingImages` / `generateLibraryAllImages` /
`generateLibraryChapterImage` (verified: only the last is referenced, by the component we
rewrite). Checkpoint-path wrappers (`getComicStatus`, `generateMissingImages`, …) untouched.

Poll loop: **2.5s base**, back off to 5–8s if `chapters_done` stalls 3 polls, reset on
advance. Each poll with non-empty `chapter_images` → `persist()` via existing
`setStoryChapterImages` (store keeps other chapters, verified at library-store.ts:103) and
update `progress = {done: chapters_done, total: total_chapters}`. Stop on
`done`/`error`/`cancelled`; `provider==="none"` or `count===0 && done` → existing
`noProvider` Settings prompt. `useEffect` cleanup stops polling on unmount.
`apiFetch` already returns JSON for any non-204 2xx, so `202` needs no client special-case.

**Reload-resume UI: scoped OUT of Phase B (recommended).** After reload the FE re-derives
per-chapter state from localStorage as today; the backend already supports reattach
(`already_running` returns the live `job_id`), so persisting `job_id` + reattaching is a
clean Phase C follow-up with **no further backend change**.

### 2.7 Migration / back-compat
**Fully async, no sync fallback.** A `≤1 chapter` sync special-case adds a second response
shape the FE must branch on — not worth it (a 1-chapter job completes in seconds, ~2-3
polls). The only caller is `LibraryComicGenerator.tsx`, rewritten in the same PR. The
checkpoint route's `GenerateImagesResponse` is unchanged.

### 2.8 Files to touch
| File | Est. diff | Work |
|---|---|---|
| `api/image_routes.py` | ~+180 / −40 | New models + `_LibraryJob` store + `_run_library_job` worker + `_resolve_target_chapters` helper; rewrite `generate_library_images` to submit-only (`202`); add `get_library_job` (GET) + `cancel_library_job` (DELETE). `handle_generate_images`, `_PayloadOrchWrapper`, `_to_media_url`, `_payload_to_story_draft` reused unchanged. |
| `frontend/lib/api/illustration.ts` | ~+70 / −55 | Add job interfaces + 3 wrappers; delete 3 dead wrappers; checkpoint wrappers untouched. |
| `frontend/components/library/LibraryComicGenerator.tsx` | ~+60 / −40 | `runChapters`→`runJob` (submit→poll→persist); `useEffect` poll cleanup; handlers pass mode opts. `setStoryChapterImages` consumed unchanged. |
| `services/handlers.py`, `library-store.ts`, `client.ts`, checkpoint routes | — | **No change.** |

---

## 3. Scope & effort

| # | Task | Size | MVP? | Note |
|---|------|------|------|------|
| 1 | Backend start-job endpoint (`202 + job_id`, work off request thread) | L | ✅ | Core. |
| 2 | Backend status endpoint (state, per-chapter progress, partial `chapter_images`) | M | ✅ | Lock contract day 1. |
| 3 | FE polling loop + incremental persist | M | ✅ | Owns "save as we go". |
| 4 | Backend reattach support (`already_running` → live `job_id`) | S | ✅ | **FE reattach UI deferred to Phase C** (locked §7.1). |
| 5 | "No provider" pre-flight + clear errors | S | ✅ | Retires the "Internal Server Error" class. |
| 6 | Single-chapter regenerate via job | S–M | ➖ | Phase A regenerate already covers v1. |
| 7 | Cancel a running job (`DELETE`) | S–M | ✅ | **In scope** (locked §7.2) — completes disconnect safety. |
| 8 | Tests: long-run completes, partial-save survives reload, error surfaces, no stranded state | M | ✅ | Map 1:1 to acceptance criteria. |

> **Note on task 4:** the *backend* enables reattach on day one (return existing `job_id` +
> `already_running`). The PM proposal lists FE reattach as MVP; the technical design
> recommends deferring the **FE reattach UI** to Phase C because localStorage already
> preserves completed chapters and `only_missing` re-submit recovers the rest. **CEO
> decision point** — see below.

**Cut order if tight:** Cancel (7) → regenerate-via-job (6) → rich progress estimates
(degrade to "chapter X of N", never cut progress entirely). **Not cuttable:** the async
spine (1–3, 5) + the partial-save/no-stranded-state tests in 8.

**Confidence this fits one sprint:** ~70%, contingent on the in-process job model (no new
queue infra). Biggest schedule lever: lock the status-endpoint contract on day 1 so FE and
backend build in parallel.

---

## 4. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Job lost on server restart | Med | High | FE is source of truth for finished chapters (localStorage); poll `404` → `interrupted (resumable)` + Resume. Restart is *recoverable*, not invisible (explicit non-goal). |
| Page reload mid-job | High | Med | Backend reattach via `already_running`; FE re-derives from localStorage. |
| Provider fails mid-run | Med | High | Per-chapter `error` + continue policy; distinct user-facing error, never "Internal Server Error". |
| localStorage write fails (quota) | Low–Med | High | Detect write failure per chapter; stop + warn ("storage full") instead of silent art loss. Long comics with many images are a real quota risk. |
| Two tabs on same story | Low | Med | Idempotent per-chapter saves; last-writer-wins (deterministic output). |
| Multi-worker deploy breaks in-process store | Low | High | Document **single-Uvicorn-worker** as a deployment constraint; persisted store is Phase C. |
| Eng design slips | Med | High | Tasks 1–2 gate all; stub the status contract day 1 for parallel FE work. |

---

## 5. Success metrics

| Metric | Today | Target | Window |
|---|---|---|---|
| Timeout / "Internal Server Error" on multi-chapter generation | Non-zero | **Zero** | 2 weeks |
| Multi-chapter runs reaching a terminal state (no stranded "in progress") | Fragile under tab close | **≥95%** | 30 days |
| Runs surviving a tab close/reload | ~0% | Majority recover (verify in test; instrument if cheap) | 30 days |
| Time-to-first-illustrated-chapter | Gated by full request | Unblocked — ch.1 renders without waiting on the whole story | Launch |
| Stranded "generating forever" states | Possible | **Zero** | Ongoing |

---

## 6. Rollout
- **Back-compat:** Phase A is the fallback. Ship Phase B behind a single boolean switch in
  the generation entry point; revert instantly if the async path misbehaves. No data
  migration — both paths write the same chapter shape to localStorage.
- **Gate checklist before making Phase B default:**
  - [ ] Long multi-chapter story generates end-to-end, no timeout / 500.
  - [ ] Close tab mid-run → completed chapters persist; (if FE reattach in scope) running
        job resumes.
  - [ ] Reload mid-run → no duplicate regeneration of saved chapters.
  - [ ] No provider → clear message, no job, no bogus 500.
  - [ ] Forced mid-run provider failure → chapter marked `error`, run reaches terminal
        state, siblings continue per policy.
  - [ ] Server restart mid-run → story resolves to `interrupted (resumable)`, never an
        infinite spinner.
  - [ ] localStorage quota exceeded → explicit warning, no silent art loss.
- Keep Phase A reachable for one release as a safety net, then remove the dead path in a
  follow-up.

---

## 7. Decisions (locked by CTO, 2026-06-09)
The CEO delegated these calls. Final for the implementer:

1. **FE reattach-on-reload → DEFER to Phase C.** Backend builds reattach support in Phase B
   (return existing `job_id` + `already_running` — cheap, no extra work), but the
   *frontend* reattach UI is **out of scope this sprint**. Rationale: localStorage already
   preserves completed chapters and `only_missing` re-submit recovers the rest, so the
   "don't babysit" promise is met for v1 without it; deferring lifts sprint confidence
   above 70%. ⇒ Scope task 4 drops to **backend-only**.
2. **Cancel endpoint (DELETE) → INCLUDE in Phase B.** Cheap (S), completes the
   disconnect-safety story. ⇒ Task 7 becomes **MVP**.
3. **Dedup response → existing `job_id` + `already_running` (200)** for identical scope;
   **409 only** for conflicting-but-different scope. Locked.
4. **Deployment → single Uvicorn worker confirmed** (`app.py:397`, no `workers=`). The
   in-process job store is valid. Documented as a deployment constraint: if the app ever
   scales to multiple workers, the store moves to a persisted backend (Phase C).
