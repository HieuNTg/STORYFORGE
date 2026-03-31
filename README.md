```
 ____ _____ ___  ______   _______ ___  ____   ____ _____
/ ___|_   _/ _ \|  _ \ \ / /  ___/ _ \|  _ \ / ___| ____|
\___ \ | || | | | |_) \ V /| |_ | | | | |_) | |  _|  _|
 ___) || || |_| |  _ < | | |  _|| |_| |  _ <| |_| | |___
|____/ |_| \___/|_| \_\|_| |_|   \___/|_| \_\\____|_____|
```

# STORYFORGE — AI Story Generation Pipeline

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Alpine.js](https://img.shields.io/badge/Alpine.js-8BC0D0.svg?logo=alpine.js&logoColor=white)](https://alpinejs.dev)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> **StoryForge** turns a one-sentence idea into a complete, drama-enhanced story with video-ready storyboards — powered by any OpenAI-compatible LLM.

---

## What is StoryForge?

Most AI writing tools generate flat, predictable stories. You get characters who never surprise you and plots that follow the path of least resistance.

StoryForge is different. It runs a **3-layer pipeline** where characters become autonomous AI agents that interact, confront, and betray each other in a drama simulation. The simulation discovers conflicts the author never planned — then rewrites the story around them.

The result: stories with genuine dramatic tension, not just grammatically correct prose.

---

## Key Features

- **3-Layer Pipeline** — generation → drama simulation → video storyboard, fully automated
- **Autonomous Character Agents** — each character acts independently based on personality, goals, and relationships
- **Drama Simulation** — AI agents interact in rounds; conflicts, betrayals, and alliances emerge organically
- **Quality Scoring** — auto-scored on 4 dimensions: coherence, character depth, drama, writing quality (1–5)
- **Agent Review Board** — 5 specialist AI critics evaluate and improve the story after each layer
- **Smart Model Routing** — cheap model for analysis, main model for writing (~45% cost savings)
- **Checkpoint & Resume** — save progress at any layer, resume on interruption
- **Export** — PDF, EPUB, or ZIP with all assets
- **Real-time Streaming** — watch chapters being written live in the browser

---

## Screenshots

> _Coming soon — run the app locally to see the UI._

<!-- Uncomment when screenshots are available:
| Create Story | Pipeline Running | Reader |
|:---:|:---:|:---:|
| ![Create](screenshots/01-create.png) | ![Running](screenshots/02-running.png) | ![Reader](screenshots/03-reader.png) |

| Analytics | Export | Settings |
|:---:|:---:|:---:|
| ![Analytics](screenshots/04-analytics.png) | ![Export](screenshots/05-export.png) | ![Settings](screenshots/06-settings.png) |
-->

---

## Quick Start

### Prerequisites

- Python 3.10+
- API key from any OpenAI-compatible provider

### Install

```bash
git clone https://github.com/HieuNTg/novel-auto.git
cd novel-auto
pip install -r requirements.txt
```

### Run

```bash
python app.py
# Web UI at http://localhost:7860
```

### First Run

1. **Settings** → choose your AI provider, enter API key, select a model
2. **Create Story** → pick genre, writing style, describe your idea
3. **Run Pipeline** → watch generation, simulation, and storyboarding in real-time
4. **Reader** → read the finished story chapter by chapter
5. **Export** → download as PDF, EPUB, or ZIP

---

## How It Works

**Layer 1 — Story Generation**

Create characters with personality, backstory, and motivations. Build the world. Generate chapter outlines. Write full chapters with rolling context that tracks character states and plot events across the entire story.

**Layer 2 — Drama Enhancement**

Each character becomes an autonomous AI agent. Agents interact across multiple simulation rounds — forming alliances, confronting rivals, discovering secrets. The system extracts dramatic situations from the simulation and rewrites the story with a higher drama score.

**Layer 3 — Video Script**

Generate shot-by-shot storyboards: camera angles, movement, mood. Create AI image generation prompts for each shot. Produce voice-over scripts with emotional cues and detailed visual descriptions for every scene.

```
Idea → [Layer 1: Write] → [Layer 2: Simulate] → [Layer 3: Storyboard] → Export
         Characters          Agent Conflicts       Camera Angles           PDF
         World-building       Drama Rewrite         Image Prompts          EPUB
         Chapters             Quality Score         Voice-over             ZIP
```

---

## Configuration

All settings are managed through the web UI at **Settings**:

| Setting | Description | Default |
|:--------|:------------|:--------|
| **AI Provider** | OpenAI, Gemini, Anthropic, OpenRouter, Ollama, or Custom | OpenAI |
| **API Key** | Your LLM provider key | — |
| **Model** | Primary model for story writing | `gpt-5.4-nano` |
| **Secondary Model** | Budget model for summaries & analysis | _(same as primary)_ |
| **Temperature** | Creativity level (0.0 – 1.0) | `0.8` |

Config is persisted to `data/config.json`.

---

## Compatible API Providers

Works with any provider exposing an OpenAI-compatible `/v1/chat/completions` endpoint:

| Provider | Models | Notes |
|:---------|:-------|:------|
| **OpenAI** | GPT-5.4, o3, o4-mini | Default provider |
| **Google Gemini** | Gemini 2.5, 3.1 | Via OpenAI-compatible endpoint |
| **Anthropic** | Haiku 4.5, Sonnet 4.6, Opus 4.6 | Via OpenAI-compatible endpoint |
| **OpenRouter** | 290+ models | Free tier available |
| **Ollama** | Any local model | Free, runs locally |
| **Custom** | Any compatible model | Provide base URL |

---

## Tech Stack

| Layer | Technology |
|:------|:-----------|
| Backend | Python 3.10+, FastAPI, Uvicorn |
| Frontend | Alpine.js 3, Tailwind CSS, vanilla JS |
| Streaming | Server-Sent Events (SSE) via fetch + ReadableStream |
| Storage | JSON files, sessionStorage (client-side) |
| Export | ReportLab (PDF), ebooklib (EPUB), zipfile |
| LLM | Any OpenAI-compatible API |

---

## Project Structure

```
storyforge/
├── app.py                        # FastAPI server + web UI
├── config.py                     # Configuration management
├── api/                          # REST API routes
│   ├── config_routes.py          #   Settings CRUD, connection test
│   ├── pipeline_routes.py        #   Pipeline SSE streaming + resume
│   └── export_routes.py          #   PDF, EPUB, ZIP export
├── web/                          # Frontend (Alpine.js + Tailwind)
│   ├── index.html                #   Single-page application
│   └── js/                       #   JavaScript modules
├── models/
│   └── schemas.py                # Pydantic data models
├── services/
│   ├── llm_client.py             # LLM API client
│   ├── llm_cache.py              # Response cache
│   ├── quality_scorer.py         # 4-dimension quality scoring
│   └── prompts.py                # Prompt templates
├── pipeline/
│   ├── orchestrator.py           # 3-layer pipeline orchestrator
│   ├── layer1_story/             # Story generation
│   ├── layer2_enhance/           # Drama simulation & enhancement
│   ├── layer3_video/             # Storyboard & script generation
│   └── agents/                   # AI review board
│       ├── drama_critic.py
│       ├── continuity_checker.py
│       ├── character_specialist.py
│       ├── dialogue_expert.py
│       └── editor_in_chief.py
└── docs/                         # Technical documentation
```

---

## License

[MIT](LICENSE) — Copyright 2026 StoryForge Contributors
