# System Architecture

## High-Level Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│ Novel Auto: Three-Layer Content Generation Pipeline              │
└─────────────────────────────────────────────────────────────────┘

Input: Genre + Story Idea + Config
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ ONBOARDING (Phase 19)                                            │
│ - OnboardingManager: 4-step wizard (genre→chars→style→confirm)  │
│ - State machine; config pre-populated before pipeline starts    │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 1: Story Generation (StoryGenerator)                       │
│ - Generate characters, world, chapter outlines                   │
│ - RAG Knowledge Base: Inject world/character context (Phase 13) │
│ - Parallel chapter writing with rolling context                  │
│ - Character State Tracking: mood, arc, knowledge per chapter    │
│ - Track plot events for continuity (cap 50)                     │
│ - CoT Self-Review: Identify weak chapters (<3.0/5.0), auto-revise│
│ - Character Visual Profiles: Save & load appearance + reference │
│   images for consistent image generation (Phase 14)             │
│ - Long-Context LLM: Token counting & context-window awareness   │
│   (Phase 15); full chapter handling via long_context_client     │
│ - Adaptive Prompts: 12 genre-specific + 4 score-booster prompts │
│   injected per chapter via AdaptivePrompts service (Phase 18)   │
│ Output: StoryDraft (chapters + character_states + plot_events)  │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ KNOWLEDGE GRAPH (Phase 19)                                       │
│ - StoryKnowledgeGraph: Index entities from L1 output            │
│ - Nodes: characters, locations, events; edges: relationships    │
│ - NetworkX-compatible; pure Python fallback                     │
│ Output: Entity graph (extensible for prompt injection)          │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ QUALITY METRICS: Scoring Layer 1                                 │
│ - QualityScorer: LLM-as-judge, 4 dimensions (1-5 scale)        │
│ - Parallel scoring (max 3 workers), sequential context          │
│ Output: StoryScore (per-chapter breakdown, weakest chapter)     │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ QUALITY GATE: L1→L2 (Phase 18)                                  │
│ - QualityGate: inline score check between layers                │
│ - Configurable threshold (quality_gate_threshold, 1.0-5.0)     │
│ - Blocks L2 if L1 score < threshold; emits gate event           │
│ Output: Gate pass/fail; ProgressTracker event emitted           │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 2: Drama Enhancement (multi-agent)                         │
│ - 6+ agents: character consistency, continuity, dialogue,       │
│   drama critic, editor-in-chief (+ more)                        │
│ - Dependency Graph (Phase 13): 4-tier execution via AgentDAG    │
│ - Multi-agent debate protocol (Phase 16): 3-round consensus     │
│   on story decisions via debate_response() callbacks            │
│ - Context-aware escalation patterns (feedback loop)             │
│ Output: Enhanced StoryDraft + agent feedback metadata           │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ SMART CHAPTER REVISION (Phase 17)                                │
│ - SmartRevisionService: Auto-detect weak chapters (score        │
│   < smart_revision_threshold, 1.0-5.0 scale)                   │
│ - Aggregate agent review guidance per chapter (regex-filtered)  │
│ - LLM revises with targeted issues/suggestions                  │
│ - Re-score to validate: accept if delta >= +0.3                │
│ - Max 2 passes per chapter; feature gated                       │
│ Output: Refined chapters + revision metadata (score deltas)     │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ QUALITY METRICS: Scoring Layer 2                                 │
│ - Same 4 dimensions; computes delta vs Layer 1                  │
│ Output: StoryScore layer=2 + improvement delta                  │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ QUALITY GATE: L2→L3 (Phase 18)                                  │
│ - Same QualityGate; checks L2 score before video storyboarding  │
│ Output: Gate pass/fail; pipeline abort or proceed to L3         │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 3: Video Storyboarding                                     │
│ - Scene-level breakdown (shots per chapter)                     │
│ - Camera directions & visual metadata                           │
│ Output: Storyboard + VideoScript                                │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ INTERACTIVE FEATURES (Layer 2+)                                  │
│ StoryBrancher   → DAG-based multi-path story exploration         │
│ WattpadExporter → Direct Wattpad/NovelHD chapter export          │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ EXPORT SERVICES                                                  │
│ VideoExporter  → SRT, voiceover, image prompts, CapCut, CSV, ZIP│
│ HTMLExporter   → Self-contained HTML reader                      │
│ TTSGenerator   → Multi-provider (edge-tts, kling, xtts) MP3/WAV │
│                  XTTS v2 voice cloning per character (Phase 13)  │
│                  Emotion-aware rate/pitch adjustment (Phase 15)  │
│ ImageGenerator → DALL-E / SD / Seedream / Replicate IP-Adapter  │
│                  Character-consistent images via reference       │
│                  images & frozen visual descriptions (Phase 14)  │
│ EmotionClassifier→ Rule-based Vietnamese emotion detection       │
│                  No LLM calls; outputs confidence scores (P15)  │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ PROGRESS TRACKER (Phase 20)                                      │
│ - ProgressTracker: structured event emission throughout pipeline │
│ - Events: gate_checked, revision_done, scoring_complete, etc.   │
│ - Integrates with Gradio progress callbacks                     │
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

### AdaptivePrompts (services/adaptive_prompts.py) — Phase 18

```
AdaptivePrompts
├─ get_genre_prompt(genre: str) → str
│  └─ Returns genre-specific emphasis prompt from 12 genre templates
│     (romance, mystery, fantasy, sci-fi, thriller, drama, comedy,
│      horror, historical, action, slice-of-life, literary)
├─ get_score_booster(dimension: str) → str
│  └─ Returns booster prompt for weak dimension (4 templates):
│     coherence_booster, character_booster, drama_booster, writing_booster
├─ build_adaptive_prompt(genre, quality_scores) → str
│  └─ Combines genre emphasis + score-booster for lowest-scoring dimension
└─ Integration: generator.py _build_chapter_prompt() appends adaptive prompt
```

**Purpose**: Genre-aware prompt tuning + quality-directed emphasis reduce LLM drift.
**Config**: Enabled automatically when `preset_profile` or explicit `genre` is set.

### QualityGate (services/quality_gate.py) — Phase 18

```
QualityGate
├─ __init__(threshold: float, enabled: bool)
│  └─ threshold: 1.0-5.0; enabled from config.enable_quality_gate
├─ check(story_score: StoryScore, layer: int) → GateResult
│  ├─ Compare story_score.overall vs threshold
│  ├─ Emit structured event via ProgressTracker
│  └─ Return: GateResult(passed, score, threshold, layer)
└─ Raises: QualityGateError if score < threshold and enabled=True
```

**Integration**: Called by orchestrator between L1→L2 and L2→L3 transitions.
**Config**: `enable_quality_gate` (bool, default: False), `quality_gate_threshold` (float).

### OnboardingManager (services/onboarding.py) — Phase 19

```
OnboardingManager
├─ __init__() — 4-step state machine; step index + collected config
├─ step_genre(genre: str) → OnboardingState
│  └─ Step 1: Set genre; advance to step 2
├─ step_characters(character_specs: list[dict]) → OnboardingState
│  └─ Step 2: Collect character specs; advance to step 3
├─ step_style(style: str, writing_style: str) → OnboardingState
│  └─ Step 3: Set style/tone; advance to step 4
├─ step_confirm(num_chapters: int) → PipelineConfig
│  └─ Step 4: Confirm + return populated PipelineConfig
├─ reset() → void
└─ current_step: int (0-3); is_complete: bool
```

**Integration**: UI wizard tab calls steps sequentially; on complete, PipelineConfig auto-populated.
**Purpose**: Reduces first-run misconfiguration; guides users through mandatory fields.

### StoryKnowledgeGraph (services/knowledge_graph.py) — Phase 19

```
StoryKnowledgeGraph
├─ __init__() — initializes graph (NetworkX DiGraph if available, else pure Python dict)
├─ index_story(story_draft: StoryDraft) → void
│  ├─ Extract character nodes from story_draft.characters
│  ├─ Extract location nodes from WorldSetting
│  ├─ Extract event nodes from plot_events
│  └─ Build edges: character→event, character→location, event→event (sequence)
├─ get_character_relationships(name: str) → list[dict]
│  └─ Returns all edges where character is source or target
├─ get_entity_context(entity_name: str) → str
│  └─ Formatted context string for prompt injection (future use)
├─ export_graph() → dict
│  └─ Serializable dict: {nodes: [...], edges: [...]}
└─ Dependencies: networkx (optional); fallback to adjacency dict if absent
```

**Integration**: Called after L1 story generation; graph available for entity-aware prompt injection in future phases.
**Pure Python fallback**: If networkx not installed, uses internal adjacency dict — zero hard dependencies added.

### ProgressTracker (services/progress_tracker.py) — Phase 20

```
ProgressTracker
├─ __init__(callback: Optional[Callable] = None)
│  └─ callback: Gradio progress function or custom sink
├─ emit(event: str, data: dict) → void
│  ├─ Structured event: {event, timestamp, data}
│  ├─ Logs at INFO level
│  └─ Calls callback if registered
├─ Standard events:
│  ├─ "gate_checked"     — QualityGate result (layer, passed, score)
│  ├─ "revision_done"    — SmartRevision result (revised_count, score_deltas)
│  ├─ "scoring_complete" — QualityScorer result (layer, overall, weakest)
│  ├─ "layer_start"      — layer N starting
│  └─ "layer_complete"   — layer N done
└─ Integration: orchestrator injects ProgressTracker; services call tracker.emit()
```

**Purpose**: Structured telemetry throughout pipeline; Gradio progress bar integration; extensible for future monitoring/analytics.

### SelfReviewService (services/self_review.py)

```
SelfReviewService
├─ __init__() — integrates with cheap model tier
├─ review_chapter(chapter: Chapter, context: StoryContext) → ChapterReview
│  ├─ CoT prompt: identify weaknesses (dialogue, pacing, character consistency)
│  ├─ CAI: inject self-critique + revision request
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

### RAGKnowledgeBase (services/rag_knowledge_base.py) — Phase 13

```
RAGKnowledgeBase
├─ __init__(persist_dir) — ChromaDB + sentence-transformers
├─ add_file(filepath: str) → void
│  ├─ Read .txt, .md, .pdf (10 MB max, graceful degradation)
│  ├─ Chunk: 500-char sentences, 50-char overlap
│  └─ Embed + store in ChromaDB
├─ add_documents(docs: list[str]) → void
├─ query(prompt: str, top_k: int = 5) → list[str]
├─ clear() → void
├─ count() → int
└─ Graceful Degradation: silently no-op if chromadb/sentence-transformers absent
```

**Config**: `rag_enabled`, `rag_persist_dir`; no LLM calls (local sentence-transformers).

### StoryBrancher (services/story_brancher.py)

```
StoryBrancher
├─ fork_at_chapter(branch_point, variations) → list[Branch]
├─ merge_branches(branches, merge_strategy) → Chapter
├─ export_multipath_story() → dict
├─ save_tree(tree: StoryTree, filename="") → str     [Phase 10]
├─ load_tree(path: str) → StoryTree                  [Phase 10]
├─ list_saved_trees() → list[dict]                   [Phase 10]
└─ Constraints: in-memory + local JSON; max 10 branches/story
```

### WattpadExporter (services/wattpad_exporter.py)

```
WattpadExporter
├─ export_chapters(chapters, metadata) → list[dict]
│  ├─ reading_time_min per chapter (words/200, min 1)  [Phase 10]
│  └─ character_appendix in metadata                   [Phase 10]
├─ export_zip(output_dir) → str                        [Phase 10]
└─ Local export only (Wattpad API deprecated 2023)
```

### TTSAudioGenerator (services/tts_audio_generator.py) — Phase 13 XTTS

```
TTSAudioGenerator
├─ __init__(provider, voice, rate, pitch, character_voice_map)
│  └─ provider: "edge-tts" | "kling" | "xtts" | "none"
├─ generate_chapter_audio(chapter, character_name) → str  # MP3/WAV path
│  ├─ XTTS: POST multipart to Coqui/Replicate + reference audio per character
│  ├─ Emotion-aware: rate (0.8-1.2×) + pitch (-20 to +20 semitones) [Phase 15]
│  └─ Fallback: XTTS failure → retry edge-tts
├─ character_voice_map: { "CharacterName": "voice_key" }
└─ list_voices(lang="vi") → list[str]
```

### ImageGenerator (services/image_generator.py) — Phase 14 Character Consistency

```
ImageGenerator
├─ generate_panel_image(prompt, panel_number) → Optional[str]
│  └─ providers: none | dalle | sd-api | seedream | replicate
├─ generate_with_reference(prompt, reference_paths, filename)
│  └─ Routes to seedream/replicate for character-consistent generation
└─ batch_generate(image_prompts) → list[Optional[str]]
   └─ ThreadPoolExecutor (max 3 workers)
```

### ReplicateIPAdapter (services/replicate_ip_adapter.py) — Phase 14

```
ReplicateIPAdapter
├─ generate(prompt, reference_image_path, filename)
│  ├─ Encode reference image as base64 data URI
│  ├─ POST to Replicate /v1/predictions
│  └─ Poll for completion (3-sec intervals, 120-sec timeout)
└─ Model: tencentarc/ip-adapter-faceid-sdxl (default)
```

### CharacterVisualProfileStore (services/character_visual_profile.py) — Phase 14

```
CharacterVisualProfileStore
├─ save_profile(name, appearance_desc, reference_image_path)
├─ load_profile(name) → Optional[dict]
├─ get_reference_image(name) → Optional[str]
├─ get_visual_description(name) → str   # frozen description for prompt injection
├─ build_visual_description(character) → str
└─ Storage: output/characters/{safe_name}/profile.json + images
```

### CreditManager (services/credit_manager.py)

```
CreditManager
├─ create_account(username, password) → Account   # bcrypt.hashpw
├─ authenticate(username, password) → bool
├─ get_balance(username) → int
├─ deduct(username, amount) → bool
├─ top_up(username, amount) → int
└─ audit_log(username) → list[Transaction]
```

### TokenCounter (services/token_counter.py) — Phase 15

```
TokenCounter
├─ estimate_tokens(text: str, model: str) → int   # ~4 chars per token
├─ fits_in_context(text, model, context_limit) → bool
└─ Context windows: GPT-4/4o (128k), 3.5-turbo (4k), deepseek (4k)
```

### LongContextClient (services/long_context_client.py) — Phase 15

```
LongContextClient
├─ generate(prompt, max_tokens) → str   # 3 retries, exponential backoff
├─ generate_stream(prompt) → Iterator[str]
└─ Config: use_long_context, long_context_model, long_context_base_url, timeout
```

### EmotionClassifier (services/emotion_classifier.py) — Phase 15

```
EmotionClassifier
├─ classify(text: str) → EmotionResult
│  └─ Rule-based Vietnamese; emotions: joy, sadness, anger, fear, neutral
└─ Output: {emotion, confidence (0.0-1.0)}
```

### DebateOrchestrator (pipeline/agents/debate_orchestrator.py) — Phase 16 / 16.5

```
DebateOrchestrator
├─ run_debate(agents, story_draft, layer, round1_reviews) → DebateResult
│  ├─ Round 1: Initial AgentReview scores
│  ├─ Round 2: LLM-powered debate_response() — challenge/support peers + revised_score
│  └─ Round 3: Final vote; consensus_score computed
└─ Max rounds: configurable via max_debate_rounds
```

**Phase 16.5**: DebateEntry includes `revised_score`; DramaCritic + CharacterSpecialist use LLM prompts (DRAMA_DEBATE, CHARACTER_DEBATE). A/B threshold: 0.10.

### SmartRevisionService (services/smart_revision.py) — Phase 17

```
SmartRevisionService
├─ revise_weak_chapters(enhanced_story, quality_scores, reviews, genre, progress_callback)
│  ├─ Identify: ChapterScore.overall < smart_revision_threshold
│  ├─ Aggregate guidance: _aggregate_review_guidance() via regex word-boundary
│  └─ [LOOP max_passes]: LLM revise → re-score → accept if delta >= +0.3
└─ _aggregate_review_guidance(chapter_number, reviews) → (issues, suggestions)
   └─ Cap: 5 issues + 5 suggestions per chapter
```

**Config**: `enable_smart_revision` (default False), `smart_revision_threshold` (default 3.5).

## CI/CD Pipeline (GitHub Actions)

```
.github/workflows/ci.yml
│
├─ Trigger: push / PR → main
│
├─ Jobs (parallel — Phase 20):
│  ├─ lint       — flake8 --max-line-length=120
│  ├─ typecheck  — mypy --strict (key services + models)
│  └─ test       — pytest tests/ -v --cov  (22 E2E tests included)
│
├─ Job: build-validate (after test)
│  └─ python -c "import app" (smoke import check)
│
└─ Job: staging-deploy (after build-validate) [Phase 20]
   └─ Deploy to staging via docker-compose.staging.yml
```

**Phase 20**: lint/typecheck/test now run in parallel (not sequential); staging-deploy job added after successful build.

## Credit System Architecture

```
User Request
  ↓
CreditManager.authenticate()
  ↓
CreditManager.deduct(cost_estimate)
  ├─ Insufficient → raise InsufficientCreditsError → UI shows top-up prompt
  └─ OK → proceed
         ↓
  PipelineOrchestrator.run_pipeline()
         ↓
  [On completion] log audit entry
  [On failure]    refund partial credits
```

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
    │   ├─ Prompt includes rolling context (summaries, char states, plot events)
    │   └─ AdaptivePrompts.build_adaptive_prompt() appended [Phase 18]
    │
    ├─→ [PARALLEL] ThreadPoolExecutor(max_workers=3):
    │   ├─→ summarize_chapter()
    │   ├─→ extract_character_states()  (temp=0.3, max_tokens=1000)
    │   └─→ extract_plot_events()       (temp=0.3, max_tokens=1000)
    │
    ├─→ [OPTIONAL] Self-Review (if enable_self_review):
    │   └─→ SelfReviewService.review_chapter() → ChapterReview
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
   └─ generate() with json_mode=True → Parse + Pydantic validate
```

## Agent Architecture (Layer 2)

```
BaseAgent (abstract)
├─ review(output, layer, iteration, prior_reviews) → AgentReview
├─ debate_response(story_draft, layer, own_review, all_reviews) → list[DebateEntry]
├─ _parse_debate_llm_response(result, all_reviews) → list[DebateEntry]  [Phase 16.5]
├─ _get_chapter_excerpt(story_draft, max_chars) → str                   [Phase 16.5]
└─ Subclasses: CharacterSpecialist, ContinuityChecker, DialogueExpert,
               DramaCritic, EditorInChief

AgentRegistry
├─ run_review_cycle(story_draft, context) → list[AgentReview]
└─ Wires debate + smart revision when config flags enabled
```

### Agent Dependency Graph (AgentDAG) — Phase 13

```
Tier 1: CharacterSpecialist (no deps)
Tier 2: Continuity, Dialogue, StyleCoordinator, PacingExpert
Tier 3: DramaCritic, DialogueBalance
Tier 4: EditorInChief (depends on all)
```

Tiered execution via ThreadPoolExecutor; Kahn's algorithm for topological sort.

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

- **VideoExporter**: `export_all(output_dir)` → ZIP (SRT, voiceover, image_prompts, capcut_draft.json, timeline.csv); max 200 panels
- **HTMLExporter**: `export(output_dir)` → self-contained `.html` (dark/light, chapter nav, character cards)
- **TTSAudioGenerator**: `generate_chapter_audio(chapter)` → MP3 path
- **ImageGenerator**: `batch_generate(prompts)` → list of image paths

## Configuration Management

```
PipelineConfig:
   ├─ num_chapters, words_per_chapter, genre, style
   ├─ context_window_chapters (default: 2)
   ├─ Layer 2: num_simulation_rounds, num_agents, drama_intensity
   ├─ Layer 3: shots_per_chapter, video_style
   ├─ language: "vi" | "en"
   ├─ enable_self_review (bool, default: False)               [Phase 10]
   ├─ self_review_threshold (float 1.0-5.0, default: 3.0)    [Phase 10]
   ├─ rag_enabled, rag_persist_dir                            [Phase 13]
   ├─ xtts_api_url, xtts_reference_audio, character_voice_map [Phase 13]
   ├─ enable_character_consistency (bool, default: False)     [Phase 14]
   ├─ replicate_api_key, character_consistency_provider       [Phase 14]
   ├─ use_long_context, long_context_model, long_context_base_url [Phase 15]
   ├─ long_context_timeout_seconds (int, default: 120)        [Phase 15]
   ├─ enable_voice_emotion (bool, default: False)             [Phase 15]
   ├─ enable_agent_debate (bool, default: False)              [Phase 16]
   ├─ max_debate_rounds (int, default: 3)                     [Phase 16]
   ├─ enable_smart_revision (bool, default: False)            [Phase 17]
   ├─ smart_revision_threshold (float 1.0-5.0, default: 3.5) [Phase 17]
   ├─ enable_quality_gate (bool, default: False)              [Phase 18]
   ├─ quality_gate_threshold (float 1.0-5.0)                 [Phase 18]
   └─ preset_profile ("beginner" | "advanced" | "pro")       [Phase 18]
```

**Phase 18**: Quality gate blocks inter-layer transitions if score < threshold; preset profiles pre-populate common config bundles.
**Phase 19**: OnboardingManager state machine populates PipelineConfig from 4-step wizard; StoryKnowledgeGraph built post-L1 (no new config fields — automatic).
**Phase 20**: ProgressTracker injected by orchestrator; docker-compose.staging.yml + parallel CI + staging-deploy job (infra-only, no new PipelineConfig fields).

## Error Handling

- **LLM**: Transient (429, 5xx) → retry/backoff; non-transient (4xx) → fail fast
- **Quality Gate**: Score < threshold → `QualityGateError` surfaced to UI; pipeline aborted
- **Extraction**: Parse error → log + skip; fallback to empty list
- **Credits**: `InsufficientCreditsError` → surface to UI, pipeline aborted
- **TTS/Image**: Provider error → log warning, skip; pipeline continues
- **Knowledge Graph**: networkx absent → pure Python fallback; no error

## Token Budget

| Operation | Temp | Max Tokens | Notes |
|-----------|------|-----------|-------|
| Chapter writing | 0.8 | 4096 | Creative, high variance |
| State extraction | 0.3 | 1000 | Compact, consistent |
| Chapter scoring | 0.2 | 500 | Deterministic |
| Summarization | 0.3 | 500 | Brief |
| Debate response | 0.5 | 800 | LLM-powered analysis |
| Smart revision | 0.7 | 4096 | Targeted chapter rewrite |

---

**Architectural Principle**: Modular layers with clear handoffs. Each service is independently testable. Phase 18 adds inline quality gates between layers and genre-adaptive prompts. Phase 19 adds guided onboarding and entity knowledge graph. Phase 20 adds structured progress telemetry and production-parity staging infrastructure.

**Last Updated**: 2026-03-25 | **Version**: 2.4 (Phase 18-20: Quality Gate, Adaptive Prompts, Onboarding, Knowledge Graph, Staging, Progress Tracker)
