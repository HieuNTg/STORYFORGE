<p align="center">
  <img src="web/img/logo.png" alt="StoryForge" width="80" />
</p>

<h1 align="center">StoryForge</h1>

<p align="center">
  <strong>AI-powered story generation pipeline with autonomous character agents</strong>
</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python 3.10+" /></a>
  <a href="https://fastapi.tiangolo.com"><img src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white" alt="FastAPI" /></a>
  <a href="https://alpinejs.dev"><img src="https://img.shields.io/badge/Alpine.js-8BC0D0?logo=alpine.js&logoColor=white" alt="Alpine.js" /></a>
  <img src="https://img.shields.io/badge/tests-1362%20passed-brightgreen" alt="Tests" />
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License" /></a>
</p>

<p align="center">
  Turn a one-sentence idea into a complete, drama-enhanced story with video-ready storyboards.<br />
  Powered by any OpenAI-compatible LLM.
</p>

---

## Why StoryForge?

Most AI writing tools produce flat, predictable stories. StoryForge takes a different approach: characters become **autonomous AI agents** that interact, confront, and betray each other in a drama simulation. The simulation discovers conflicts the author never planned — then rewrites the story around them.

```
Idea ─→ Layer 1: Generate ─→ Layer 2: Simulate ─→ Layer 3: Storyboard ─→ Export
         Characters            Agent Conflicts       Camera Angles           PDF
         World-building         Drama Rewrite         Image Prompts          EPUB
         Full Chapters          Quality Score         Voice Scripts          ZIP
```

---

## Features

| Category | Capabilities |
|:---------|:-------------|
| **Pipeline** | 3-layer automation (write → simulate → storyboard), checkpoint & resume, real-time SSE streaming |
| **AI Agents** | Autonomous character agents with personality-driven behavior; 5-critic review board |
| **Drama Engine** | Multi-round agent simulation, conflict/alliance emergence, iterative drama scoring |
| **Voice Mode** | Text-to-speech narration via edge-tts (no API key), in-browser audio player |
| **Branch Reader** | Choose-your-own-adventure mode with LLM-generated branching paths |
| **Smart Routing** | Per-layer model selection, cheap model for analysis / premium for writing (~45% cost savings) |
| **Quality** | 4-dimension scoring (coherence, character, drama, writing), automated re-enhancement loop |
| **Export** | PDF, EPUB, ZIP with all assets |
| **Analytics** | Pipeline metrics, A/B testing, performance dashboards |

---

## Quick Start

```bash
# Clone & install
git clone https://github.com/HieuNTg/novel-auto.git
cd novel-auto
pip install -r requirements.txt

# Run
python app.py
# → http://localhost:7860
```

### First Run

1. **Settings** → choose AI provider, enter API key, select model
2. **Create Story** → pick genre, style, describe your idea
3. **Run Pipeline** → watch generation, simulation, storyboarding in real-time
4. **Reader** → read the finished story or try Branch Mode
5. **Export** → download as PDF, EPUB, or ZIP

---

## The Pipeline

### Layer 1 — Story Generation

Characters with personality, backstory, and motivations. World-building. Chapter outlines. Full chapters written with rolling context that tracks character states and plot events across the entire story. Optional long-context mode for models with 1M+ token windows.

### Layer 2 — Drama Enhancement

Each character becomes an autonomous AI agent. Agents interact across simulation rounds — forming alliances, confronting rivals, discovering secrets. The system extracts dramatic situations and rewrites the story with higher drama scores. Iterative feedback re-enhances weak chapters until they pass the drama threshold.

### Layer 3 — Video Storyboard

Shot-by-shot storyboards with camera angles, movement, and mood. AI image generation prompts for each shot. Voice-over scripts with emotional cues. Location descriptions and sound design.

---

## Configuration

All settings managed through the web UI (**Settings** tab):

| Setting | Description | Default |
|:--------|:------------|:--------|
| AI Provider | OpenAI, Gemini, Anthropic, OpenRouter, Ollama, Custom | OpenAI |
| Model | Primary model for writing | `gpt-4o` |
| Secondary Model | Budget model for summaries & analysis | _(same as primary)_ |
| Layer Models | Per-layer model override (Layer 1/2/3) | _(primary)_ |
| Temperature | Creativity level (0.0 – 1.0) | `0.8` |

Config persisted to `data/config.json`.

### Compatible Providers

Any provider exposing an OpenAI-compatible `/v1/chat/completions` endpoint:

**OpenAI** · **Google Gemini** · **Anthropic** · **OpenRouter** (290+ models) · **Ollama** (local) · **Any custom endpoint**

---

## Tech Stack

| Layer | Technology |
|:------|:-----------|
| Backend | Python 3.10+, FastAPI, Uvicorn |
| Frontend | Alpine.js 3, Tailwind CSS |
| Streaming | Server-Sent Events (SSE) |
| AI | Any OpenAI-compatible API, edge-tts |
| Storage | JSON files, SQLite (cache) |
| Export | ReportLab (PDF), ebooklib (EPUB) |

---

## Project Structure

```
storyforge/
├── app.py                          # FastAPI entry point
├── config.py                       # Configuration (singleton)
├── api/                            # REST API routes
│   ├── pipeline_routes.py          #   Pipeline SSE streaming + resume
│   ├── config_routes.py            #   Settings CRUD + connection test
│   ├── export_routes.py            #   PDF, EPUB, ZIP export
│   ├── audio_routes.py             #   TTS generation + streaming
│   ├── branch_routes.py            #   Interactive branch reader
│   ├── analytics_routes.py         #   Pipeline analytics
│   └── ab_routes.py                #   A/B testing
├── web/                            # Frontend (Alpine.js + Tailwind)
│   ├── index.html                  #   Single-page application
│   └── js/                         #   JS modules (audio, branch, etc.)
├── models/schemas.py               # Pydantic data models
├── services/
│   ├── llm/                        #   LLM client (singleton, fallback chain)
│   ├── browser_auth/               #   Browser-based auth
│   ├── branch_narrative.py         #   Branch reader engine
│   ├── tts_audio_generator.py      #   Text-to-speech
│   ├── quality_scorer.py           #   4-dimension scoring
│   └── prompts.py                  #   Prompt templates
├── pipeline/
│   ├── orchestrator.py             #   3-layer pipeline orchestrator
│   ├── layer1_story/               #   Story generation
│   ├── layer2_enhance/             #   Drama simulation & enhancement
│   ├── layer3_video/               #   Storyboard & script
│   └── agents/                     #   AI review board (5 critics)
├── tests/                          # 1362 tests
└── docs/                           # Technical documentation
```

---

## License

[MIT](LICENSE) — Copyright 2026 StoryForge Contributors
