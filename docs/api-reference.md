# StoryForge API Reference

All routes are mounted under `/api` (unversioned) and mirrored under `/api/v1` (versioned, adds `X-API-Version: v1` response header).

---

## Quick Reference

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/auth/register` | No | Create account, returns JWT |
| POST | `/api/auth/login` | No | Authenticate, returns JWT |
| GET | `/api/auth/me` | Yes | Current user profile |
| GET | `/api/config` | No | Read current LLM/pipeline config |
| PUT | `/api/config` | No | Save LLM/pipeline settings |
| POST | `/api/config/test-connection` | No | Test LLM connectivity |
| GET | `/api/config/languages` | No | Supported UI languages |
| GET | `/api/config/presets` | No | Pipeline presets list |
| POST | `/api/config/presets/{key}` | No | Apply a pipeline preset |
| GET | `/api/config/model-presets` | No | Model presets list |
| POST | `/api/config/model-presets/{key}` | No | Apply a model preset |
| GET | `/api/config/cache-stats` | No | LLM cache statistics |
| DELETE | `/api/config/cache` | No | Clear LLM cache |
| POST | `/api/pipeline/run` | No | Run full pipeline (SSE stream) |
| POST | `/api/pipeline/resume` | No | Resume from checkpoint (SSE stream) |
| GET | `/api/pipeline/genres` | No | Available genres, styles, drama levels |
| GET | `/api/pipeline/templates` | No | Story templates by genre |
| GET | `/api/pipeline/checkpoints` | No | List saved checkpoints |
| GET | `/api/pipeline/checkpoints/{filename}` | No | Load a checkpoint |
| DELETE | `/api/pipeline/checkpoints/{filename}` | No | Delete a checkpoint |
| POST | `/api/export/files/{session_id}` | No | Export story files (TXT/MD/JSON) |
| POST | `/api/export/zip/{session_id}` | No | Export all files as ZIP download |
| POST | `/api/export/pdf/{session_id}` | No | Export story as PDF download |
| POST | `/api/export/epub/{session_id}` | No | Export story as EPUB download |
| POST | `/api/audio/generate/{chapter_index}` | No | Generate TTS audio for chapter |
| GET | `/api/audio/stream/{filename}` | No | Stream audio file (MP3) |
| GET | `/api/audio/status/{chapter_index}` | No | Check audio existence for chapter |
| POST | `/api/analytics/onboarding/step` | No | Record onboarding step completion |
| POST | `/api/analytics/onboarding/dropout` | No | Record onboarding dropout |
| GET | `/api/analytics/onboarding` | No | Onboarding funnel summary |
| POST | `/api/branch/start` | No | Start a branching narrative session |
| GET | `/api/branch/{session_id}/current` | No | Current node + choices |
| POST | `/api/branch/{session_id}/choose` | No | Choose a branch (generates via LLM) |
| POST | `/api/branch/{session_id}/back` | No | Navigate to parent node |
| GET | `/api/branch/{session_id}/tree` | No | Full branch tree structure |
| GET | `/api/dashboard` | No | Dashboard HTML page |
| GET | `/api/dashboard/summary` | No | Aggregated metrics summary |
| GET | `/api/dashboard/test-timings` | No | CI test timing data |
| POST | `/api/feedback` | No | Submit story rating + comment |
| GET | `/api/feedback/{story_id}` | Yes | Get all feedback for a story |
| POST | `/api/ab/experiments` | Yes | Create A/B experiment |
| GET | `/api/ab/experiments` | No | List all experiments |
| POST | `/api/ab/experiments/{id}/assign` | No | Assign variant to session |
| POST | `/api/ab/experiments/{id}/result` | Yes | Record experiment outcome |
| GET | `/api/ab/experiments/{id}/results` | No | Aggregated results by variant |
| GET | `/api/metrics` | No | Prometheus metrics (text/plain) |
| GET | `/api/metrics/prometheus` | No | StoryForge Prometheus metrics |

---

## Authentication

### `POST /api/auth/register`

Create a new user account. Returns a JWT bearer token.

**Request body:**
```json
{
  "username": "alice",
  "password": "securepass123"
}
```

Validation: username 3–32 chars, alphanumeric/underscore. Password 8–128 chars.

**Response `201`:**
```json
{
  "access_token": "eyJhbGci...",
  "token_type": "bearer",
  "username": "alice",
  "user_id": "usr_abc123"
}
```

**Error `409`** — username already taken.

---

### `POST /api/auth/login`

Authenticate an existing user.

**Request body:** same as register.

**Response `200`:** same shape as register response.

**Error `401`** — invalid credentials.

---

### `GET /api/auth/me`

Return the profile of the currently authenticated user.

**Headers:** `Authorization: Bearer <token>`

**Response `200`:**
```json
{
  "user_id": "usr_abc123",
  "username": "alice",
  "created_at": "2025-01-01T00:00:00"
}
```

**Error `401`** — missing/invalid token. **`404`** — user not found.

---

## Configuration

### `GET /api/config`

Return current configuration. API key is masked.

**Response `200`:**
```json
{
  "llm": {
    "api_key_masked": "sk-a***key1",
    "base_url": "https://openrouter.ai/api/v1",
    "model": "gpt-4o-mini",
    "temperature": 0.8,
    "max_tokens": 4096,
    "cheap_model": "gpt-3.5-turbo",
    "cheap_base_url": null,
    "backend_type": "api",
    "layer1_model": null,
    "layer2_model": null,
    "layer3_model": null
  },
  "pipeline": {
    "language": "vi",
    "enable_self_review": true,
    "self_review_threshold": 0.7
  }
}
```

---

### `PUT /api/config`

Save settings to `config.json`. All fields are optional (patch semantics).

**Request body:**
```json
{
  "api_key": "sk-...",
  "base_url": "https://openrouter.ai/api/v1",
  "model": "openai/gpt-4o-mini",
  "temperature": 0.8,
  "max_tokens": 4096,
  "cheap_model": "openai/gpt-3.5-turbo",
  "cheap_base_url": null,
  "backend_type": "api",
  "language": "vi",
  "layer1_model": null,
  "layer2_model": null,
  "layer3_model": null,
  "enable_self_review": true,
  "self_review_threshold": 0.7
}
```

**Response `200`:** `{"status": "ok"}`

---

### `POST /api/config/test-connection`

Verify the configured LLM is reachable.

**Response `200`:**
```json
{"ok": true, "message": "Connected to gpt-4o-mini"}
```

---

### `GET /api/config/languages`

**Response `200`:**
```json
{"languages": ["vi", "en", "zh"], "current": "vi"}
```

---

### `GET /api/config/presets`

**Response `200`:**
```json
{
  "presets": {
    "fast": {"label": "Nhanh (ít chương, ít agent)"},
    "balanced": {"label": "Cân bằng"},
    "quality": {"label": "Chất lượng cao"}
  }
}
```

---

### `POST /api/config/presets/{key}`

Apply a named pipeline preset. Returns `404` if key not found.

**Response `200`:** `{"status": "ok", "label": "Cân bằng"}`

---

### `GET /api/config/model-presets`

**Response `200`:**
```json
{
  "presets": {
    "openrouter_free": {"label": "OpenRouter Free Tier"},
    "openai_gpt4o": {"label": "OpenAI GPT-4o"}
  }
}
```

---

### `POST /api/config/model-presets/{key}`

Apply a named model preset (sets `base_url`, `model`, etc.). Returns `404` if not found.

**Response `200`:** `{"status": "ok", "label": "OpenRouter Free Tier"}`

---

### `GET /api/config/cache-stats`

**Response `200`:**
```json
{"total_entries": 142, "size_bytes": 204800, "hit_rate": 0.73}
```

---

### `DELETE /api/config/cache`

**Response `200`:** `{"status": "ok"}`

---

## Pipeline

### `POST /api/pipeline/run`

Run the full 3-layer story generation pipeline. Response is an **SSE stream** (`text/event-stream`). The story idea must be at least 10 characters.

**Request body:**
```json
{
  "title": "",
  "genre": "Tiên Hiệp",
  "style": "Miêu tả chi tiết",
  "idea": "Một thanh niên bình thường thức dậy với sức mạnh bí ẩn...",
  "num_chapters": 5,
  "num_characters": 5,
  "word_count": 2000,
  "num_sim_rounds": 3,
  "drama_level": "cao",
  "shots_per_chapter": 8,
  "enable_agents": true,
  "enable_scoring": true,
  "enable_media": false
}
```

**SSE event types:**

| Event type | Payload |
|------------|---------|
| `session` | `{"type": "session", "session_id": "140..."}` |
| `log` | `{"type": "log", "data": "Đang tạo nhân vật...", "logs_count": 3}` |
| `stream` | `{"type": "stream", "data": "<partial LLM text>"}` |
| `done` | `{"type": "done", "data": { ...full summary... }}` |
| `error` | `{"type": "error", "data": "Story idea is too short..."}` |

The `done` payload contains the full output summary including chapters, characters, storyboard, scores, and session metadata.

---

### `POST /api/pipeline/resume`

Resume a previously interrupted pipeline run from a checkpoint. Returns the same SSE event stream as `/run`.

**Request body:**
```json
{"checkpoint": "checkpoint_20250101_abc123.json"}
```

The filename must be a plain filename (no path separators). Returns `error` SSE event if checkpoint not found.

---

### `GET /api/pipeline/genres`

**Response `200`:**
```json
{
  "genres": ["Tiên Hiệp", "Huyền Huyễn", "Kiếm Hiệp", "..."],
  "styles": ["Miêu tả chi tiết", "Đối thoại nhiều", "Hành động nhanh", "Lãng mạn", "Tối tăm"],
  "drama_levels": ["thấp", "trung bình", "cao"]
}
```

---

### `GET /api/pipeline/templates`

**Response `200`:**
```json
{
  "Tiên Hiệp": [
    {"title": "Truyền Thuyết Kiếm Tiên", "idea": "..."}
  ]
}
```

Returns `{}` if no template file is found.

---

### `GET /api/pipeline/checkpoints`

**Response `200`:**
```json
{
  "checkpoints": [
    {
      "label": "checkpoint_abc.json (2025-01-01, 142KB)",
      "path": "checkpoint_abc.json",
      "title": "Truyện Tiên Hiệp",
      "genre": "Tiên Hiệp",
      "chapter_count": 5,
      "current_layer": 2,
      "size_kb": 142,
      "modified": "2025-01-01 12:00:00"
    }
  ]
}
```

---

### `GET /api/pipeline/checkpoints/{filename}`

Load a single checkpoint and return the formatted story summary (same shape as the `done` SSE event). Includes extra fields: `source: "library"`, `filename`.

**Errors:** `400` invalid filename / path traversal, `404` not found, `500` parse error.

---

### `DELETE /api/pipeline/checkpoints/{filename}`

Delete a checkpoint file.

**Response `200`:** `{"ok": true, "deleted": "checkpoint_abc.json"}`

**Errors:** `400` invalid filename, `404` not found.

---

## Export

All export endpoints require a valid `session_id` from an active pipeline run. A session expires when the SSE stream closes.

### `POST /api/export/files/{session_id}`

Export story in one or more text formats.

**Query params (repeated):** `formats=TXT&formats=Markdown&formats=JSON`

Default: `["TXT", "Markdown", "JSON"]`

**Response `200`:**
```json
{"files": ["/app/output/story_abc.txt", "/app/output/story_abc.md"]}
```

**Error `404`** — session not found.

---

### `POST /api/export/zip/{session_id}`

Export all formats (TXT, Markdown, JSON, HTML) as a ZIP archive. Returns file download.

**Response:** `application/zip` binary download named `storyforge_export.zip`.

---

### `POST /api/export/pdf/{session_id}`

Export story as PDF. Returns file download.

**Response:** `application/pdf` binary download named `storyforge.pdf`.

---

### `POST /api/export/epub/{session_id}`

Export story as EPUB e-book. Returns file download.

**Response:** `application/epub+zip` binary download named `storyforge.epub`.

---

## Audio (TTS)

### `POST /api/audio/generate/{chapter_index}`

Generate text-to-speech audio for a chapter using Microsoft Edge TTS.

**Path param:** `chapter_index` — zero-based chapter index.

**Request body:**
```json
{
  "text": "Chapter content goes here...",
  "voice": "vi-VN-HoaiMyNeural"
}
```

`voice` is optional; defaults to `vi-VN-HoaiMyNeural`.

**Response `200`:**
```json
{"status": "ok", "audio_url": "/api/audio/stream/chapter_000.mp3"}
```

**Error `400`** — text is empty. **`500`** — TTS generation failed.

---

### `GET /api/audio/stream/{filename}`

Serve a generated audio file.

**Response:** `audio/mpeg` stream.

**Error `400`** — invalid filename (path traversal attempt). **`404`** — file not found.

---

### `GET /api/audio/status/{chapter_index}`

Check whether audio has been generated for a chapter.

**Response `200`:**
```json
{
  "chapter_index": 0,
  "exists": true,
  "audio_url": "/api/audio/stream/chapter_000.mp3"
}
```

`audio_url` is `null` when `exists` is `false`.

---

## Analytics

### `POST /api/analytics/onboarding/step`

Record a completed onboarding step. Body: `{"session_id": "...", "step": "configure_llm", "duration_ms": 4200}`. Limits: session_id ≤64, step ≤128, duration_ms 0–3,600,000.

**Response `200`:** `{"status": "ok"}`

---

### `POST /api/analytics/onboarding/dropout`

Record abandonment at a step. Body: `{"session_id": "...", "step": "configure_llm"}`.

**Response `200`:** `{"status": "ok"}`

---

### `GET /api/analytics/onboarding`

Return funnel aggregation across all sessions.

**Response `200`:** `{"funnel": {"configure_llm": {"completions": 42, "dropouts": 8}, ...}}`

---

## Branching Narrative

### `POST /api/branch/start`

Create a new choose-your-own-adventure session from existing story text. Returns `201`.

**Request body:**
```json
{
  "text": "Truyện bắt đầu với một buổi sáng bình thường...",
  "genre": "Tiên Hiệp"
}
```

`text` 10–20,000 chars. `genre` max 64 chars.

**Response `201`:**
```json
{
  "session_id": "br_abc123",
  "node": {
    "id": "root",
    "text": "...",
    "choices": ["Chọn con đường bên trái", "Tiếp tục thẳng", "Quay lại"]
  }
}
```

---

### `GET /api/branch/{session_id}/current`

Return the current node.

**Response `200`:** `{"node": { "id": "...", "text": "...", "choices": [...] }}`

**Error `404`** — session not found.

---

### `POST /api/branch/{session_id}/choose`

Select a choice. If the branch has not been visited before, the continuation is generated via LLM.

**Request body:**
```json
{"choice_index": 1}
```

`choice_index` 0–9.

**Response `200`:**
```json
{
  "node": {"id": "...", "text": "...", "choices": [...]},
  "generated": true
}
```

`generated: false` when the node was already cached. **Error `400`** — choice index out of range. **`502`** — LLM generation failed.

---

### `POST /api/branch/{session_id}/back`

Navigate to the parent node.

**Response `200`:** `{"node": {...}}`

**Error `400`** — already at root. **`404`** — session not found.

---

### `GET /api/branch/{session_id}/tree`

Return the full decision tree for visualization.

**Response `200`:** `{"nodes": [...], "edges": [...]}`

---

## Dashboard

### `GET /api/dashboard`

Serve the analytics dashboard HTML page.

**Response:** `text/html`

---

### `GET /api/dashboard/summary`

Aggregated metrics parsed from Prometheus exposition.

**Response `200`:**
```json
{
  "pipeline": {"total": 120, "success": 115, "error": 5, "active": 2},
  "llm": {"total_requests": 4800, "total_errors": 12},
  "quality": {"buckets": {"0.5": 20, "0.7": 80, "0.9": 15}, "sum": 82.4, "count": 120},
  "onboarding": {"funnel": {...}},
  "timestamp": 1735689600.0
}
```

---

### `GET /api/dashboard/test-timings`

Return the latest CI test timing data (written by the test runner to `data/test_timings.json`).

**Response `200`:**
```json
{
  "tests": [{"name": "test_pipeline", "duration": 2.3}],
  "timestamp": "2025-01-01T12:00:00",
  "total_duration": 45.2
}
```

Returns `{"tests": [], "timestamp": null}` if the file does not exist.

---

## Feedback

### `POST /api/feedback`

Submit a star rating and optional comment for a generated story. No auth required. Returns `201`.

**Request body:**
```json
{
  "story_id": "checkpoint_abc.json",
  "rating": 4,
  "comment": "Great plot twists!"
}
```

`rating` 1–5. `comment` max 2,000 chars.

**Response `201`:** `{"status": "ok", "story_id": "checkpoint_abc.json"}`

---

### `GET /api/feedback/{story_id}`

Retrieve all feedback for a story. **Auth required.**

**Response `200`:**
```json
{
  "story_id": "checkpoint_abc.json",
  "entries": [
    {"story_id": "...", "rating": 4, "comment": "...", "submitted_at": 1735689600.0}
  ],
  "average_rating": 4.25,
  "count": 4
}
```

**Error `404`** — no feedback found.

---

## A/B Testing

### `POST /api/ab/experiments`

Create experiment. **Auth required.** Body: `{"name": "drama_test", "variants": ["control", "high_drama"]}` (min 2 variants). Returns `201`: `{"experiment_id": "exp_abc123"}`. Error `400` on duplicate name.

---

### `GET /api/ab/experiments`

List all experiments with metadata.

**Response `200`:** `{"experiments": [{"id": "...", "name": "...", "variants": [...], "created_at": "..."}]}`

---

### `POST /api/ab/experiments/{experiment_id}/assign`

Return deterministic variant for a session. Body: `{"session_id": "sess_xyz"}`.

**Response `200`:** `{"variant": "high_drama"}`

---

### `POST /api/ab/experiments/{experiment_id}/result`

Record outcome. **Auth required.** Body: `{"session_id": "sess_xyz", "metric": "completion_rate", "value": 1.0}`. Returns `201`: `{"status": "ok"}`.

---

### `GET /api/ab/experiments/{experiment_id}/results`

Per-variant aggregated metrics.

**Response `200`:** `{"results": {"control": {"completion_rate": {"mean": 0.72, "count": 50}}, ...}}`

---

## Metrics

### `GET /api/metrics`

Prometheus text format (version 0.0.4) with pipeline, LLM, and quality histogram metrics.

**Response:** `text/plain; version=0.0.4` (raw Prometheus exposition).

---

### `GET /api/metrics/prometheus`

StoryForge application metrics in Prometheus format:

- `storyforge_requests_total`
- `storyforge_request_duration_seconds`
- `storyforge_pipeline_runs_total`
- `storyforge_active_sse_connections`
- `storyforge_uptime_seconds`

**Response:** `text/plain; version=0.0.4`

---

## Versioned API (`/api/v1`)

Every route above is also available under `/api/v1/` (e.g. `POST /api/v1/pipeline/run`). Versioned responses include an additional response header:

```
X-API-Version: v1
```

The v1 router excludes the A/B testing and metrics routes. The feedback sub-router under v1 returns placeholder responses pending full implementation.
