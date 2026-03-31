# StoryForge

**Automatically generate dramatic stories and video scripts with AI.**

A 3-layer pipeline that turns ideas into complete stories, simulates characters to increase drama, then exports video scripts with detailed storyboards.

---

## Pipeline

```
Idea → [Layer 1: Story Generation] → [Layer 2: Drama Simulation] → [Layer 3: Video Script] → Output
```

### Layer 1 — Story Generation

- Create characters with personality, backstory, and motivations
- Build world settings (world-building)
- Generate detailed chapter outlines
- Write chapters automatically with rolling context (tracking character state, plot events)
- Real-time streaming preview while writing

### Layer 2 — Drama Enhancement

- Analyze relationships and conflicts between characters
- Each character becomes an autonomous AI agent — interacting, confronting, betraying
- Extract dramatic situations from simulation
- Rewrite story with higher drama score

### Layer 3 — Video Script

- Generate storyboard: shot type, camera movement, mood
- Create image prompts for AI image generation
- Voice-over script with emotions
- Character and setting visual descriptions

---

## Features

| Feature | Description |
|---|---|
| **Character State Tracking** | Track character state across chapters (mood, actions, relationships) |
| **Model Routing** | Use cheap model for summaries/analysis, main model for writing — saves ~45% cost |
| **Streaming Preview** | Watch AI write each chapter in real-time |
| **File Export** | Export PDF, EPUB, ZIP — download individual files or everything |
| **Quality Metrics** | Auto-score on 4 dimensions: coherence, character, drama, writing (1-5) |
| **Agent Review** | AI review board evaluates quality after each layer |
| **Checkpoint/Resume** | Save progress, resume pipeline from any layer |
| **LLM Cache** | Cache LLM responses, reduce cost on re-runs |

---

## Installation

### Requirements

- Python 3.10+
- API key from an OpenAI-compatible provider (OpenAI, Google Gemini, Anthropic, OpenRouter, Ollama, etc.)

### Setup

```bash
git clone https://github.com/HieuNTg/novel-auto.git
cd novel-auto
pip install -r requirements.txt
```

### Run

```bash
python app.py
```

Open your browser at `http://localhost:7860`

---

## Configuration

Go to the **Settings** page in the web UI:

| Setting | Description | Default |
|---|---|---|
| AI Provider | Choose from OpenAI, Gemini, Anthropic, OpenRouter, Ollama, or Custom | OpenAI |
| API Key | Key from your LLM provider | — |
| Model | Main model (for writing) | `gpt-5.4-nano` |
| Secondary Model | Cheap model (for summaries, analysis) | _(blank = use main model)_ |
| Temperature | Creativity level | `0.8` |

Configuration is saved to `data/config.json`.

---

## Project Structure

```
storyforge/
├── app.py                          # FastAPI + Web UI
├── config.py                       # Configuration management
├── api/                            # REST API routes
│   ├── __init__.py                 # Router registry
│   ├── config_routes.py            # Settings CRUD, connection test
│   ├── pipeline_routes.py          # Pipeline SSE streaming
│   ├── export_routes.py            # PDF, EPUB, ZIP export
│   └── account_routes.py           # Login/register
├── web/                            # Frontend (Alpine.js + Tailwind)
│   ├── index.html                  # Single-page app
│   └── js/                         # JavaScript modules
├── models/
│   └── schemas.py                  # Pydantic models
├── services/
│   ├── llm_client.py               # LLM API client
│   ├── llm_cache.py                # Cache LLM responses
│   ├── quality_scorer.py           # Story quality scoring
│   └── prompts.py                  # Prompt templates
├── pipeline/
│   ├── orchestrator.py             # 3-layer pipeline orchestrator
│   ├── layer1_story/
│   │   └── generator.py            # Story generation from scratch
│   ├── layer2_enhance/
│   │   ├── analyzer.py             # Character relationship analysis
│   │   ├── simulator.py            # AI agent simulation
│   │   └── enhancer.py             # Drama enhancement rewrite
│   ├── layer3_video/
│   │   └── storyboard.py           # Storyboard & script generation
│   └── agents/                     # AI review board
│       ├── agent_registry.py
│       ├── drama_critic.py
│       ├── continuity_checker.py
│       ├── character_specialist.py
│       ├── dialogue_expert.py
│       └── editor_in_chief.py
├── requirements.txt
└── docs/                           # Technical documentation
```

---

## Usage

1. **Setup API** — Go to Settings, choose your AI provider, enter API key, and select a model
2. **Enter your idea** — Choose genre, writing style, describe your story idea
3. **Configure** — Number of chapters, characters, words per chapter, drama level
4. **Run Pipeline** — Click the button, watch progress in real-time
5. **View results** — Tabs: Draft, Enhanced, Simulation, Quality
6. **Export** — Download PDF, EPUB, or ZIP

---

## Compatible APIs

Supports any OpenAI-compatible API:

- OpenAI (GPT-5.4, o3, o4-mini)
- Google Gemini (Gemini 2.5, 3.1 via OpenAI-compatible endpoint)
- Anthropic Claude (Haiku 4.5, Sonnet 4.6, Opus 4.6)
- OpenRouter (290+ models, free options available)
- Ollama (local, free)
- Any provider with a `/v1/chat/completions` endpoint

---

## License

MIT
