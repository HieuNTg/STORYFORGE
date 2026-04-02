# StoryForge Architecture

## 1. System Overview

```mermaid
flowchart LR
    subgraph Client
        B[Browser\nAlpine.js + Tailwind]
    end

    subgraph Backend["FastAPI Backend (port 7860)"]
        R[API Router\n/api + /api/v1]
        P[Pipeline\nOrchestrator]
        A[Agent\nRegistry]
        LLM[LLM Client\nService]
    end

    subgraph Providers["LLM Providers"]
        OAI[OpenAI / GPT-4o]
        OR[OpenRouter\nFree & Paid]
        LOCAL[Local Ollama /\nCustom API]
    end

    subgraph Storage["Data Storage"]
        JSON[JSON Files\nconfig.json\ncheckpoints/\nstory_templates.json]
        SQLITE[SQLite Cache\nllm_cache.db]
        AUDIO[Audio Files\ndata/audio/*.mp3]
    end

    B -- "HTTP + SSE" --> R
    R --> P
    P --> A
    P --> LLM
    A --> LLM
    LLM --> OAI
    LLM --> OR
    LLM --> LOCAL
    P -- "read/write" --> JSON
    LLM -- "read/write" --> SQLITE
    P -- "write" --> AUDIO
```

---

## 2. Three-Layer Pipeline

Story generation proceeds through three sequential layers. Each layer can be skipped or configured independently. Progress is streamed to the client via SSE.

```mermaid
flowchart TD
    START([User Submits Idea]) --> L1

    subgraph L1["Layer 1 — Story Draft"]
        CG[Character Generator\nPersonas, backstories,\nmotivations]
        WB[World Building /\nStory Bible\nSettings, rules, lore]
        OB[Outline Builder\nChapter summaries\n& story arc]
        CW[Chapter Writer\nFull prose generation\nper chapter]
        CG --> WB --> OB --> CW
    end

    CW --> L2

    subgraph L2["Layer 2 — Drama Enhancement"]
        SIM[Drama Simulator\nCharacter agents\nrun N rounds]
        EVAL[Drama Evaluator\nScore scenes,\nfind escalations]
        ENH[Story Enhancer\nRewrite weak scenes\nwith drama events]
        AR[Agent Review Cycle\n8 specialist agents\nin parallel]
        DB[Debate Orchestrator\nAgents argue\nover revisions]
        SIM --> EVAL --> ENH --> AR
        AR --> DB --> AR
    end

    ENH --> L3

    subgraph L3["Layer 3 — Video Storyboard"]
        SB[Scene Breakdown\nper chapter]
        NAR[Narration Writer\nVoiceover text]
        IP[Image Prompt\nGenerator]
        CC[CapCut Export\nProject file]
        SB --> NAR --> IP --> CC
    end

    CC --> OUT([Checkpoint saved\n+ SSE done event])
```

---

## 3. Multi-Agent System

Layer 2 uses a registry of specialist AI agents that review story output in parallel tiers, then optionally debate their findings.

```mermaid
flowchart TD
    subgraph Tier1["Tier 1 — Parallel Analysis"]
        CHR["Chuyen Gia Nhan Vat\n(character_specialist)\nCharacter consistency,\nmotivations, arcs"]
        DRA["Nha Phe Binh Kich Tinh\n(drama_critic)\nTension levels,\ndrama scoring"]
        DLG["Chuyen Gia Doi Thoai\n(dialogue_expert)\nDialogue authenticity\nand voice"]
        PAC["Phan Tich Nhip Truyen\n(pacing_analyzer)\nNarrative pacing\nand flow"]
        STY["Kiem Tra Van Phong\n(style_consistency)\nWriting style\nconsistency"]
        CON["Kiem Soat Vien\n(continuity_checker)\nPlot continuity\nand logic"]
        BAL["Can Bang Doi Thoai\n(dialogue_balance)\nDialogue-to-prose\nratio"]
    end

    subgraph Tier2["Tier 2 — Aggregation"]
        EIC["Bien Tap Truong\n(editor_in_chief)\nAggregates all reviews\ngives final verdict"]
    end

    subgraph Debate["Optional Debate (Layer 2 only)"]
        DO["Debate Orchestrator\nAgents argue competing\nrevision proposals"]
        CONS["Consensus Builder\nFinal agreed-upon\nrevision plan"]
        DO --> CONS
    end

    CHR & DRA & DLG & PAC & STY & CON & BAL --> EIC
    EIC -- "not approved" --> DO
    CONS -- "revised output" --> Tier1

    subgraph DramaSim["Drama Simulator (runs before agents)"]
        CA["Character Agents\n(one per character)"]
        TR["Trust Network\nPairwise trust 0-100"]
        EP["Escalation Patterns\nphản_bội / tiết_lộ /\nđối_đầu / hy_sinh / đảo_ngược"]
        CA -- "update" --> TR
        TR -- "trigger" --> EP
    end

    EP -- "drama events" --> CHR
```

**Agent execution model:**

- All Tier 1 agents run in parallel via `ThreadPoolExecutor`
- `editor_in_chief` always runs last (Tier 2) and aggregates prior reviews
- If `enable_agent_debate` is on, the `DebateOrchestrator` runs between review cycles on Layer 2
- Up to `max_iterations` (default 3) review cycles per layer; stops early when all agents approve
- DAG-ordered tiered execution is used when agents declare dependencies; falls back to flat-parallel on cycle detection

---

## 4. Deployment Architecture

Production deployment uses Docker Compose with four services on an isolated bridge network.

```mermaid
flowchart TB
    INTERNET([Internet]) --> NGINX

    subgraph DockerNetwork["storyforge-network (bridge)"]
        NGINX["nginx:1.25-alpine\nstoryforge-nginx\nports 80:80 / 443:443\nSSL termination + static assets"]

        APP["storyforge-app (Python/FastAPI)\nport 7860 (internal only)\n2 CPU / 2 GB RAM\nvolumes: ./data ./output ./assets"]

        PG["postgres:16-alpine\nstoryforge-postgres\nvolume: storyforge-pg-data\n1 CPU / 512 MB RAM"]

        REDIS["redis:7-alpine\nstoryforge-redis\nAOF persistence\nvolume: storyforge-redis-data\n0.5 CPU / 256 MB RAM"]

        NGINX -- "proxy_pass :7860" --> APP
        APP -- "DATABASE_URL\npostgresql://..." --> PG
        APP -- "REDIS_URL\nredis://redis:6379/0" --> REDIS
    end

    subgraph Volumes["Named Volumes"]
        PGVOL[(storyforge-pg-data)]
        REDVOL[(storyforge-redis-data)]
    end

    PG --- PGVOL
    REDIS --- REDVOL
```

**Health checks:**

| Service | Check | Interval |
|---------|-------|----------|
| postgres | `pg_isready -U storyforge` | 10 s |
| redis | `redis-cli ping` | 10 s |
| app | `GET /api/health` (HTTP 200) | 30 s |
| nginx | `wget --spider /api/health` | 30 s |

Startup order enforced by `depends_on` with `condition: service_healthy`.

---

## 5. Directory Structure

```
storyforge/
├── api/                    # FastAPI route modules
│   ├── __init__.py         # Router registry (mounts all sub-routers)
│   ├── auth_routes.py
│   ├── config_routes.py
│   ├── pipeline_routes.py  # SSE streaming, checkpoints
│   ├── export_routes.py    # PDF, EPUB, ZIP
│   ├── audio_routes.py     # TTS via edge-tts
│   ├── analytics_routes.py
│   ├── branch_routes.py    # Choose-your-own-adventure
│   ├── dashboard_routes.py
│   ├── feedback_routes.py
│   ├── ab_routes.py
│   ├── metrics_routes.py
│   └── v1/router.py        # Versioned mirror with X-API-Version header
│
├── pipeline/               # Core generation engine
│   ├── orchestrator.py     # Main entry point: run_full_pipeline()
│   ├── layer1_story/       # Draft generation
│   │   ├── character_generator.py
│   │   ├── story_bible_manager.py
│   │   ├── outline_builder.py
│   │   └── chapter_writer.py
│   ├── layer2_enhance/     # Drama enhancement
│   │   ├── simulator.py    # DramaSimulator + CharacterAgents
│   │   ├── analyzer.py
│   │   └── enhancer.py
│   ├── layer3_video/       # Storyboard generation
│   │   └── storyboard.py
│   └── agents/             # Specialist review agents
│       ├── base_agent.py
│       ├── agent_registry.py
│       ├── agent_graph.py  # DAG dependency resolver
│       ├── debate_orchestrator.py
│       ├── character_specialist.py
│       ├── drama_critic.py
│       ├── dialogue_expert.py
│       ├── pacing_analyzer.py
│       ├── style_consistency.py
│       ├── continuity_checker.py
│       ├── dialogue_balance.py
│       └── editor_in_chief.py
│
├── services/               # Shared services
│   ├── llm_client.py       # OpenAI-compatible HTTP client
│   ├── llm_cache.py        # SQLite response cache
│   ├── auth.py             # JWT creation
│   ├── user_store.py       # User persistence
│   ├── metrics.py          # Prometheus counters
│   ├── i18n.py             # Internationalisation
│   └── onboarding_analytics.py
│
├── models/schemas.py       # Pydantic data models
├── middleware/             # Auth middleware, rate limiting, CORS
├── config.py               # ConfigManager, PIPELINE_PRESETS, MODEL_PRESETS
├── app.py                  # FastAPI app factory, lifespan
├── web/                    # Static HTML/JS frontend (Alpine.js)
├── data/                   # Templates, audio, test timings
├── output/checkpoints/     # Saved pipeline state (JSON)
├── docs/                   # Project documentation
├── nginx/                  # nginx.conf, ssl-params.conf
├── Dockerfile
└── docker-compose.production.yml
```
