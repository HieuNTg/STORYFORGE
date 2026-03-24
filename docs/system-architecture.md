# System Architecture

## High-Level Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│ Novel Auto: Three-Layer Content Generation Pipeline              │
└─────────────────────────────────────────────────────────────────┘

Input: Genre + Story Idea + Config
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 1: Story Generation (StoryGenerator)                       │
│ - Generate characters, world, chapter outlines                   │
│ - Parallel chapter writing with rolling context                  │
│ - Character State Tracking: mood, arc, knowledge per chapter     │
│ - Track plot events for continuity (cap 50)                      │
│ - CoT Self-Review: Identify weak chapters (<3.0/5.0), auto-revise│
│ Output: StoryDraft (chapters + character_states + plot_events)   │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ QUALITY METRICS: Scoring Layer 1                                 │
│ - QualityScorer: LLM-as-judge, 4 dimensions (1-5 scale)         │
│ - Parallel scoring (max 3 workers), sequential context           │
│ Output: StoryScore (per-chapter breakdown, weakest chapter)      │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 2: Drama Enhancement (multi-agent)                         │
│ - 6 agents: character consistency, continuity, dialogue,         │
│   drama critic, editor-in-chief                                  │
│ - Context-aware escalation patterns (feedback loop)              │
│ Output: Enhanced StoryDraft + agent feedback metadata            │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ QUALITY METRICS: Scoring Layer 2                                 │
│ - Same 4 dimensions; computes delta vs Layer 1                   │
│ Output: StoryScore layer=2 + improvement delta                   │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 3: Video Storyboarding                                     │
│ - Scene-level breakdown (shots per chapter)                      │
│ - Camera directions & visual metadata                            │
│ Output: Storyboard + VideoScript                                 │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ INTERACTIVE FEATURES (Layer 2+)                                   │
│ StoryBrancher  → DAG-based multi-path story exploration           │
│ WattpadExporter→ Direct Wattpad/NovelHD chapter export            │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ EXPORT SERVICES                                                   │
│ VideoExporter  → SRT, voiceover, image prompts, CapCut, CSV, ZIP │
│ HTMLExporter   → Self-contained HTML reader                       │
│ TTSGenerator   → edge-tts MP3/WAV per chapter (vi voices)        │
│ ImageGenerator → DALL-E / SD panels from image prompts           │
└─────────────────────────────────────────────────────────────────┘
  ↓
Final Output: novel + enhanced story + quality scores + video assets + audio + images
```

## UI Modularization (ui/tabs/)

`app.py` is a thin shell — all tab UI logic lives in `ui/tabs/`:

```
app.py
├─ ui/tabs/pipeline_tab.py      # Genre dropdown, 13 templates, generation form
├─ ui/tabs/web_auth_tab.py      # Chrome CDP launch, credential capture/clear
├─ ui/tabs/output_tab.py        # Story draft / simulation / video storyboard
├─ ui/tabs/quality_tab.py       # ChapterScore / StoryScore display
├─ ui/tabs/export_tab.py        # TXT/MD/JSON/HTML checkboxes + ZIP download
└─ ui/tabs/continuation_tab.py  # Chapter slider, character editor, re-enhance
```

**Benefits**: each tab is independently testable; app.py only wires layout + event routing.

**Output tabs** (4): Truyen | Mo Phong | Video | Danh Gia

## New Service Layer Components

### SelfReviewService (services/self_review.py)

```
SelfReviewService
├─ __init__() — integrates with cheap model tier
├─ review_chapter(chapter: Chapter, context: StoryContext) → ChapterReview
│  ├─ CoT prompt: identify weaknesses (dialogue, pacing, character consistency)
│  ├─ CAI (Capability Analysis & Iteration): inject self-critique + revision request
│  ├─ Score: 1-5 scale; if <3.0, auto-revise with LLM feedback
│  └─ Return: quality_score, issues, revised_content (if applicable)
├─ review_story(chapters, context) → list[ChapterReview]
│  └─ Parallel (max 3 workers, cheap tier)
└─ Thresholds:
   ├─ Weak chapter: <3.0/5.0
   ├─ Revision rate: ~20-30% of chapters
   └─ Cost optimization: 1 LLM call per weak chapter
```

**Integration**: Runs post-write for Layer 1; auto-revises weak chapters before Layer 2.

### StoryBrancher (services/story_brancher.py)

```
StoryBrancher
├─ __init__() — DAG management (in-memory, Gradio State)
├─ fork_at_chapter(branch_point, variations) → list[Branch]
│  ├─ Creates multiple story paths from single chapter
│  └─ Each variation: new outline, character state overrides
├─ merge_branches(branches, merge_strategy) → Chapter
│  └─ User-driven; no auto-merge (MVP)
├─ export_multipath_story() → dict
│  └─ JSON: all branches, connections, chapter choices
└─ Constraints:
   ├─ In-memory only (no DB persistence)
   ├─ Max 10 branches per story (MVP)
   └─ User selects active path for Layer 2+
```

**Integration**: Interactive tab UI (branching_tab.py); branches exported as JSON metadata.

### WattpadExporter (services/wattpad_exporter.py)

```
WattpadExporter
├─ __init__(username, password) — optional auth for direct upload
├─ export_chapters(chapters, metadata) → list[dict]
│  ├─ Wattpad chapter format: title, parts, author_notes
│  ├─ NovelHD metadata: character bios, world worldbuilding, tags
│  └─ Character/world transcription per chapter
├─ validate_format(chapter) → bool
│  └─ Length limits, character encoding, formatting rules
└─ upload_if_authenticated() → list[str]  # chapter URLs
```

**Integration**: Export tab checkbox; outputs `.wattpad.json` + `.novelHD.json` metadata.

### TTSAudioGenerator (services/tts_audio_generator.py)

```
TTSAudioGenerator
├─ __init__(voice, rate, pitch) — defaults to Vietnamese voice
├─ generate_chapter_audio(chapter: Chapter) → str  # path to MP3/WAV
│  ├─ Split chapter content into segments
│  ├─ edge-tts synthesis per segment
│  └─ Merge + write to output/audio/
├─ list_voices(lang="vi") → list[str]
└─ Wired to all pipeline entry points via feedback loop callback
```

**Voices**: `vi-VN-HoaiMyNeural`, `vi-VN-NamMinhNeural` (and others via edge-tts discovery)
**Config**: voice, rate, pitch from PipelineConfig or env

### ImageGenerator (services/image_generator.py)

```
ImageGenerator
├─ __init__(provider, api_key, api_url)
│  └─ provider: "none" | "dalle" | "sd"
├─ generate_panel_image(prompt: str, panel_number: int) → Optional[str]
│  ├─ "none" → skip (returns None)
│  ├─ "dalle" → OpenAI images.generate() → download + save
│  └─ "sd"   → POST to IMAGE_API_URL with IMAGE_API_KEY → save
└─ batch_generate(image_prompts: list[str]) → list[Optional[str]]
   └─ ThreadPoolExecutor (max 3 workers)
```

**Provider selection**: `STORYFORGE_IMAGE_PROVIDER` env var
**Credentials**: `IMAGE_API_KEY`, `IMAGE_API_URL`

### CreditManager (services/credit_manager.py)

```
CreditManager
├─ create_account(username, password) → Account
│  └─ bcrypt.hashpw(password) stored — never plain text
├─ authenticate(username, password) → bool
│  └─ bcrypt.checkpw() verification
├─ get_balance(username) → int
├─ deduct(username, amount) → bool
│  └─ Returns False if insufficient credits
├─ top_up(username, amount) → int  # new balance
└─ audit_log(username) → list[Transaction]
```

**Integration**: `orchestrator.run_pipeline()` calls `credit_manager.deduct()` before LLM call;
raises `InsufficientCreditsError` if balance exhausted.

## CI/CD Pipeline (GitHub Actions)

```
.github/workflows/ci.yml
│
├─ Trigger: push / PR → main
│
├─ Job: lint
│  └─ flake8 --max-line-length=120
│
├─ Job: typecheck
│  └─ mypy --strict (key services + models)
│
├─ Job: test
│  ├─ pytest tests/ -v --cov
│  └─ Coverage report uploaded as artifact
│
└─ Job: build-validate
   └─ python -c "import app" (smoke import check)
```

**Escalation patterns**: test failures trigger agent feedback loop review (context-aware escalation).

## Credit System Architecture

```
User Request
  ↓
CreditManager.authenticate()
  ↓ (authenticated)
CreditManager.deduct(cost_estimate)
  ├─ Insufficient → raise InsufficientCreditsError → UI shows top-up prompt
  └─ OK → proceed
         ↓
  PipelineOrchestrator.run_pipeline()
         ↓
  [On completion] log audit entry
  [On failure]    refund partial credits
```

**Cost model**: configurable credits-per-LLM-call; TTS and image generation have separate rates.

## Layer 1: Story Generation Architecture

```
generate_full_story(title, genre, idea, num_chapters, ...)
│
├─→ generate_characters() → list[Character]
├─→ generate_world() → WorldSetting
├─→ generate_outline() → (synopsis, list[ChapterOutline])
│
└─→ [MAIN LOOP] for each chapter:
    ├─→ write_chapter(outline, context=story_context) → Chapter
    │   └─ Prompt includes rolling context (summaries, char states, plot events)
    │
    ├─→ [PARALLEL] ThreadPoolExecutor(max_workers=3):
    │   ├─→ summarize_chapter()
    │   ├─→ extract_character_states()  (temp=0.3, max_tokens=1000)
    │   └─→ extract_plot_events()       (temp=0.3, max_tokens=1000)
    │
    └─→ Update story_context:
        ├─ recent_summaries (keep last context_window_chapters)
        ├─ character_states (merge by name, latest wins)
        └─ plot_events (cap at 50)
```

## LLM Client Architecture

```
LLMClient (singleton)
├─ generate(system, user, temperature, max_tokens, json_mode) → str
│  ├─ localize_prompt(template, lang) → localized prompt
│  ├─ Cache hit? → return cached
│  ├─ branch backend_type:
│  │  ├─ "api" → OpenAI-compatible (HTTPS)
│  │  └─ "web" → DeepSeekWebClient (browser auth + PoW)
│  ├─ Retry (MAX_RETRIES=3, exponential backoff)
│  └─ Cache result
│
└─ generate_json(system, user, max_tokens) → dict
   ├─ generate() with json_mode=True
   ├─ Parse + Pydantic validate
   └─ Return dict
```

## Agent Architecture (Layer 2)

```
BaseAgent (abstract)
├─ feedback(story_draft, context) → AgentFeedback
└─ Subclasses: CharacterSpecialist, ContinuityChecker, DialogueExpert,
               DramaCritic, EditorInChief

AgentRegistry
├─ discover() → list[BaseAgent]
├─ get_by_name(name) → BaseAgent
└─ register(agent) → void
```

**Context-aware escalation**: agents detect threshold breaches (drama_intensity, coherence < 2.5)
and escalate feedback priority; orchestrator re-runs affected chapter enhancement.

## Quality Scoring Architecture

```
QualityScorer.score_story(chapters, layer)
├─ ThreadPoolExecutor(max 3 workers)
│  └─ score_chapter(chapter, prev_context) → ChapterScore
│     ├─ Excerpt: head 2600 + tail 1400 if > 4000 chars
│     ├─ LLM: SCORE_CHAPTER (temp=0.2, cheap tier, max_tokens=500)
│     └─ Clamp 1-5, compute overall (mean of 4 dimensions)
│
└─ Aggregate → StoryScore:
   ├─ avg_coherence, avg_character, avg_drama, avg_writing
   ├─ overall = mean(4 averages)
   ├─ weakest_chapter = min overall
   └─ scoring_layer = 1 | 2
```

## Export Architecture

### VideoExporter
- `export_all(output_dir)` → ZIP (SRT, voiceover, image_prompts, capcut_draft.json, timeline.csv)
- Max 200 panels; returns None on error

### HTMLExporter
- `export(output_dir)` → `.html` (self-contained, dark/light, chapter nav, character cards)

### TTSAudioGenerator
- `generate_chapter_audio(chapter)` → MP3 path

### ImageGenerator
- `batch_generate(prompts)` → list of image paths (or None if provider="none")

### Orchestrator Export Methods

```python
orchestrator.export_video_assets(output_dir)  → Optional[str]  # ZIP path
orchestrator.export_html(output_dir)          → Optional[str]  # HTML path
orchestrator.export_audio(output_dir)         → list[str]      # MP3 paths per chapter
orchestrator.export_images(output_dir)        → list[str]      # image paths per panel
```

## Configuration Management

```
ConfigManager (singleton)
├─ LLMConfig:
│  ├─ api_key, base_url, model
│  ├─ backend_type ("api" | "web"), web_auth_provider
│  ├─ temperature, max_tokens, cache settings
│  └─ cheap_model, cheap_base_url
│
└─ PipelineConfig:
   ├─ num_chapters, words_per_chapter, genre, style
   ├─ context_window_chapters (default: 2)
   ├─ Layer 2: num_simulation_rounds, num_agents, drama_intensity
   ├─ Layer 3: shots_per_chapter, video_style
   └─ language: "vi" | "en"

Environment overrides:
├─ STORYFORGE_IMAGE_PROVIDER (none | dalle | sd)
├─ IMAGE_API_KEY
└─ IMAGE_API_URL
```

## Error Handling

- **LLM**: Transient (429, 5xx) → retry/backoff; non-transient (4xx) → fail fast
- **Extraction**: Parse error → log + skip; fallback to empty list
- **Credits**: InsufficientCreditsError → surface to UI, pipeline aborted
- **TTS/Image**: Provider error → log warning, skip; pipeline continues
- **Export**: File write error → log, skip that format; ZIP still attempted

## Token Budget

| Operation | Temp | Max Tokens | Notes |
|-----------|------|-----------|-------|
| Chapter writing | 0.8 | 4096 | Creative, high variance |
| State extraction | 0.3 | 1000 | Compact, consistent |
| Chapter scoring | 0.2 | 500 | Deterministic |
| Summarization | 0.3 | 500 | Brief |

Rolling context budget: last `context_window_chapters` summaries + char states (replaced each chapter) + plot_events (cap 50).

---

**Architectural Principle**: Modular layers with clear handoffs. Each service is independently testable. Web auth, credits, TTS, and image generation are transparent to core pipeline logic. Phase 9 adds CoT self-review, interactive branching, and expanded export capabilities.

**Last Updated**: 2026-03-24 | **Version**: 1.6 (Phase 9: CoT Self-Review, Story Branching, Wattpad Export, 31 Issue Fixes)
