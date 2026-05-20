# StoryForge Codebase Summary

## Project Overview

**StoryForge** is a 2-layer LLM story generation pipeline for Vietnamese web novels.

- **Backend**: FastAPI (Python 3.10+)
- **Frontend**: Next.js 14+ React SPA with Alpine.js compatibility
- **Database**: SQLite (via SQLAlchemy + Alembic)
- **Cache**: Redis (optional), in-memory fallback
- **Export**: PDF (fpdf2), EPUB (ebooklib)

---

## Architecture Layers

### Layer 1 (L1): Story Generation
Story outline → scene decomposition → parallel chapter writing with voice profiles and conflict tracking.

**Key modules:**
- `theme_premise_generator` — thematic anchors
- `character_generator` + `voice_profiler` — character definition + dialogue voice fingerprinting
- `outline_builder` + `outline_critic` — semantic outline validation
- `conflict_web_builder` + `foreshadowing_manager` — plot continuity
- `scene_decomposer` + `scene_beat_generator` — chapter structure
- `chapter_writer` — parallel batch generation (5 chapters/batch default)
- `post_processing` — final QA pass

**Output:** Prose chapters with metadata (arc waypoints, emotional continuity, foreshadowing seeds).

### Layer 2 (L2): Drama Enhancement
Reads L1 signals (conflict, foreshadowing, character arcs) → multi-agent simulation → scene-level drama amplification.

**Key modules:**
- `analyzer` — conflict/pacing/arc analysis
- `simulator` — multi-agent debate (adaptive rounds: 3-10 based on complexity)
- `enhancer` — per-scene drama escalation
- `contract_gate` — post-enhancement validation + optional L1 chapter rewrite

**Contracts:**
- Voice preservation (drift floor: 0.3, warning: 0.4)
- Drama ceilings (genre-specific, e.g., romance ≤ 0.6)
- Character knowledge constraints (prevent hallucination)

**Signal flow:** `conflict_web`, `foreshadowing_plan` → simulator; `arc_waypoints`, `threads` → analyzer → enhancer; `voice_fingerprints` → L2 voice preservation.

---

## Frontend Architecture (Phase 4: Cinematic Reader)

### Branching & Story Graph (`frontend/components/branching/`)
- **BranchGraph.tsx**: Dagre-layout directed graph with canvas MiniMap (theme-safe, handles light/dark mode)
- **BranchNodeCard.tsx**: Interactive choice card grid (SSE-streaming branch generation state)
- **branch-stream.ts**: EventSource wrapper for `/api/branches/{id}` SSE updates

### Cinematic Reader (`frontend/app/(shell)/reader/[storyId]/[chapterId]/`)
- **Reader layout**: Illustration banner + chapter text + inline choice picker
- **IllustrationBanner.tsx**: Optional per-chapter artwork (when `enable_chapter_illustration=true`)
- **PipelineOverlay.tsx** + **PipelineLogTerminal.tsx**: Real-time generation telemetry (when `enable_pipeline_overlay=true`)

**Flow:**
1. `/reader/{storyId}/{chapterId}` renders chapter content
2. SSE-streaming from `/api/pipeline/{id}/stream` feeds overlay with (elapsed_time, tokens_used, current_layer, phase_name)
3. Choice branches displayed in cinematic grid (from `/api/branches/{id}`)

### Layout system (`frontend/lib/graph/`)
- **dagre-layout.ts**: Wraps Dagre for directed acyclic graph positioning + theme-aware canvas rendering
- **useThemeColors**: Custom hook extracting CSS variables for canvas MiniMap (avoids hardcoded colors)

---

## API Routes (Phase 4 additions)

| Endpoint | Description |
|----------|-------------|
| `POST /api/generate` | Start story generation (returns story_id) |
| `GET /api/stories/{id}` | Get story with chapters |
| `POST /api/continue/{id}` | Continue existing story |
| `GET /api/branches/{id}` | List generated branch choices (SSE-streaming) |
| `GET /api/pipeline/{id}/stream` | SSE stream of pipeline telemetry (layer, phase, elapsed, tokens) |
| `GET /api/export/{id}` | Export PDF/EPUB |
| `POST /api/forge/sentence{/stream}` | Single-sentence → story sketch (sync/streaming) |
| `POST /api/characters/generate` | 4-axis ForgeCharacter generation |
| `GET /api/config` | Get current config |
| `PUT /api/config` | Update config |
| `GET /api/health` | Health check |
| `POST /api/simulation/continue` | Continue dialogue simulation (rate-limited 10/min/IP) |
| `GET /api/simulation/{id}/transcript` | Extract simulator artifact as TranscriptTurn[] |

---

## Project Structure

```
storyforge/
├── app.py                         # FastAPI entry point
├── mcp_server.py                  # MCP server (Claude integration)
├── config/
│   ├── defaults.py                # PipelineConfig, LLMConfig dataclasses
│   ├── presets.py                 # Genre/model presets
│   └── config.py                  # ConfigManager singleton
├── pipeline/
│   ├── orchestrator.py            # Main pipeline orchestrator
│   ├── layer1_story/              # L1 modules (30+ files)
│   ├── layer2_enhance/            # L2 modules (20+ files)
│   └── agents/                    # Multi-agent debate system
├── api/                           # FastAPI routes (20+ files)
│   ├── pipeline_routes.py         # L1/L2 orchestration endpoints
│   ├── story_routes.py            # Story CRUD + export
│   └── ...
├── models/
│   ├── schemas.py                 # Pydantic request/response schemas
│   ├── narrative_schemas.py       # Story-specific schemas
│   └── db_models.py               # SQLAlchemy ORM models
├── services/                      # Business logic services
├── frontend/                      # Next.js React SPA
│   ├── app/(shell)/               # Authenticated layout
│   │   ├── reader/[storyId]/...   # Cinematic reader (Phase 4)
│   │   ├── branching/[sessionId]/ # Branch explorer (Phase 4)
│   │   └── ...
│   ├── components/
│   │   ├── branching/             # Graph + choice cards
│   │   ├── reader/                # Illustration + text
│   │   ├── pipeline/              # Overlay + terminal (Phase 4)
│   │   └── ...
│   ├── lib/
│   │   ├── api/                   # API clients (branch-stream, illustration)
│   │   ├── graph/                 # Dagre layout (useThemeColors)
│   │   └── schemas/               # Config schema validation
│   └── ...
├── tests/                         # pytest suite
└── data/                          # User data, RAG, exports
```

---

## Configuration

### Key Flags (Phase 4 additions)
| Flag | Default | Layer | Purpose |
|------|---------|-------|---------|
| `enable_pipeline_overlay` | False | Frontend | SSE-driven real-time generation telemetry UI |
| `enable_chapter_illustration` | False | L1/L2 | Trigger per-chapter auto-generated artwork |

See **CLAUDE.md** "Key Config Flags" table for complete flag list.

### Environment Variables
```bash
# Required
OPENAI_API_KEY=sk-...              # Primary LLM

# Optional LLM providers
ANTHROPIC_API_KEY=...              # Claude
GOOGLE_AI_API_KEY=...              # Gemini
ZAI_API_KEY=...                    # Z.AI (free)

# Optional services
REDIS_URL=redis://localhost:6379   # Cache
STORYFORGE_ALLOWED_ORIGINS=...     # CORS

# Image generation (Phase 4)
IMAGE_PROVIDER=none|dalle|seedream|huggingface
HF_TOKEN=...                       # HuggingFace Inference API
SEEDREAM_API_KEY=...               # ByteDance Seedream
```

---

## Build & Test

```bash
# Backend
pip install -r requirements.txt
python app.py                      # http://localhost:7860
pytest tests/ -v                   # Test suite
ruff check .                       # Linting

# Frontend (optional)
npm install
npm run dev                        # Next.js dev server
npm run lint                       # ESLint
```

---

## Key Development Guidelines

See **CLAUDE.md** for detailed behavioral guidelines (12 rules). Highlights:

1. **Think before coding** — surface assumptions; state invariants
2. **Simplicity first** — minimum code for the problem
3. **Surgical changes** — touch only what's necessary
4. **Verify before claiming done** — run the code path; show evidence
5. **Respect layer boundaries** — L1 owns story, L2 owns drama, agents own craft
6. **Config flags** — default False, remove when dead
7. **Cache & mock LLM calls** — tokens are money in production, gold in tests
8. **Async/asyncio only** — no threads in hot paths
9. **Persist via schema** — SQLAlchemy + Alembic, not side channels
10. **Communicate the diff** — lead with what changed, end with verification

---

## Testing Conventions

- Files: `tests/test_<module>.py`
- Mock all LLM calls (never real API calls in tests)
- Use `pytest-asyncio` for async tests
- Coverage target: 80%+

```python
@pytest.mark.asyncio
async def test_chapter_generation():
    config = PipelineConfig(num_chapters=1)
    result = await generate_chapter(config, chapter_num=1)
    assert result.content
```

---

## Git Workflow

- Single sprint branch → one PR to master
- Conventional commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`
- No dependabot PRs (manual updates only)
- Pre-commit hooks: ruff, pytest smoke tests

---

## Recent Changes (Phase 4)

**UI Redesign (cinematic reader + branching graph):**
- New reader route: `/reader/{storyId}/{chapterId}` with illustration banner
- Branching graph: Dagre layout + canvas MiniMap (theme-safe rendering)
- Pipeline overlay: Real-time SSE telemetry during generation
- Config flags: `enable_pipeline_overlay`, `enable_chapter_illustration`

**Deleted:**
- `frontend/components/branching/CustomBranchInput.tsx` (dead code)

See **plans/260520-1804-ui-redesign-storyforge-ai-style** for full Phase 4 details.
