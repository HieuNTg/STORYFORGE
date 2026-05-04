<h1 align="center">StoryForge</h1>

<p align="center"><strong>AI story generation with multi-agent drama simulation</strong></p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python 3.10+" /></a>
  <a href="https://fastapi.tiangolo.com"><img src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white" alt="FastAPI" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License" /></a>
  <a href="README.vi.md">Tiếng Việt</a>
</p>

<p align="center">
  Turn a one-sentence idea into a complete, drama-rich Vietnamese web novel — with character-consistent images, cinematic backgrounds, and any OpenAI-compatible LLM. Self-hosted.
</p>

<p align="center">
  <img src="assets/screenshots/v2-dark-home.png" alt="StoryForge" width="780" />
</p>

---

## Why

Most AI writers produce flat stories. StoryForge turns each character into an **autonomous agent** that argues, allies, and betrays in a multi-round drama simulation — uncovering conflicts the author never planned, then rewriting around them until quality thresholds clear.

---

## Quick Start

```bash
git clone https://github.com/HieuNTg/STORYFORGE.git
cd STORYFORGE
pip install -r requirements.txt
npm install && npm run build && npm run build:css
python app.py            # → http://localhost:7860
```

Then **Settings** (provider + API key) → **Create Story** → **Run** → **Export** (PDF/EPUB/HTML/ZIP).

---

## Features

- **2-layer pipeline** — L1 story generation → L2 drama simulation, with checkpoints, SSE streaming, optional L3 sensory polish
- **13 specialized agents** — drama critic, editor, pacing, dialogue, reader simulator, …; 6-dim LLM-as-judge auto-revision
- **Vietnamese-first** — VN names default; Chinese tiên hiệp / wuxia / xianxia and Western/Sci-Fi optional; arc scaling by chapter count
- **Continuation tools** — multi-path preview, outline editor, collaborative polish, consistency checker, mid-story insertion, retroactive fixes
- **Branch reader** — LLM-generated CYOA, SVG tree + minimap, undo/redo, bookmarks, WebSocket multi-user, EPUB tree export
- **Images** — IP-Adapter character portraits + scene backgrounds
- **Any OpenAI-compatible LLM** — OpenAI, Gemini, Anthropic, OpenRouter (290+), Z.AI, Kyma, Ollama, custom; preemptive rate-limit switching, latency-aware primary, smart cheap/premium routing (~45% saved), SQLite cache
- **Security** — CSRF double-submit, 10 MB body cap, prompt-injection middleware, encrypted secrets at rest

---

## Configuration

Settings tab persists to `data/config.json`. Key env vars:

| Variable | Purpose |
|----------|---------|
| `LLM_PROVIDER` / `LLM_API_KEY` / `LLM_MODEL` | provider, key, primary model |
| `STORYFORGE_SECRET_KEY` | HMAC key — **set in production** for encrypted secrets |
| `REDIS_URL` | required for multi-instance (`NUM_WORKERS>1`) shared cache/sessions |
| `STORYFORGE_ALLOWED_ORIGINS` | CORS origins (comma-separated) |
| `STORYFORGE_HANDOFF_STRICT` | `1` = fail-fast on malformed L1→L2 signals (default: warn) |
| `STORYFORGE_SEMANTIC_STRICT` | `1` = fail-fast on missed foreshadowing payoffs (default: warn) |
| `CHROMA_PERSIST_DIR` / `CHROMA_COLLECTION_NAME` | RAG persistence |

Per-layer model overrides, drama ceilings, batch size, voice-revert anchoring, etc. live in `config/defaults.py` (`PipelineConfig`) and the Settings UI. Agent prompts are editable in `data/prompts/agent_prompts.yaml`.

### Test markers

```bash
pytest tests/ -v -m "not calibration and not bench"   # fast subset
pytest tests/ -v -m calibration                       # real-model calibration
```

---

## Architecture

```mermaid
flowchart LR
    idea([Idea]) --> L1[L1<br/>Story Generation]
    L1 --> L2[L2<br/>Drama Enhancement]
    L2 --> media[Images · Export]
    media --> out([PDF · EPUB · HTML · ZIP])
```

L1→L2 signals: `conflict_web` + `foreshadowing_plan` feed the simulator; `arc_waypoints` + `threads` feed the analyzer/enhancer; `voice_fingerprints` preserve speaker voice through L2 rewrites.

See [`docs/system-architecture.md`](docs/system-architecture.md) for the full flow.

---

## Documentation

- [`docs/`](docs/README.md) — full index (architecture, code standards, deployment)
- [`docs/adr/`](docs/adr/) — architecture decision records
- [CONTRIBUTING.md](CONTRIBUTING.md) — dev setup, code style, PR process

---

## License

[MIT](LICENSE) — Copyright 2026 StoryForge Contributors
