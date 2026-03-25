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
│ - RAG Knowledge Base: Inject world/character context (Phase 13)  │
│ - Parallel chapter writing with rolling context                  │
│ - Character State Tracking: mood, arc, knowledge per chapter     │
│ - Track plot events for continuity (cap 50)                      │
│ - CoT Self-Review: Identify weak chapters (<3.0/5.0), auto-revise│
│ - Character Visual Profiles: Save & load appearance + reference  │
│   images for consistent image generation (Phase 14)              │
│ - Long-Context LLM: Token counting & context-window awareness    │
│   (Phase 15); full chapter handling via long_context_client      │
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
│ - 6+ agents: character consistency, continuity, dialogue,        │
│   drama critic, editor-in-chief (+ more)                         │
│ - Dependency Graph (Phase 13): 4-tier execution via AgentDAG     │
│ - Multi-agent debate protocol (Phase 16): 3-round consensus      │
│   on story decisions via debate_response() callbacks             │
│ - Context-aware escalation patterns (feedback loop)              │
│ Output: Enhanced StoryDraft + agent feedback metadata            │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ SMART CHAPTER REVISION (Phase 17)                                │
│ - SmartRevisionService: Auto-detect weak chapters (score         │
│   < smart_revision_threshold, 1.0-5.0 scale)                    │
│ - Aggregate agent review guidance per chapter (regex-filtered)   │
│ - LLM revises with targeted issues/suggestions                   │
│ - Re-score to validate: accept if delta >= +0.3                 │
│ - Max 2 passes per chapter; feature gated                        │
│ Output: Refined chapters + revision metadata (score deltas)      │
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
│ TTSGenerator   → Multi-provider (edge-tts, kling, xtts) MP3/WAV  │
│                  XTTS v2 voice cloning per character (Phase 13)   │
│                  Emotion-aware rate/pitch adjustment (Phase 15)   │
│ ImageGenerator → DALL-E / SD / Seedream / Replicate IP-Adapter   │
│                  Character-consistent images via reference        │
│                  images & frozen visual descriptions (Phase 14)   │
│ EmotionClassifier→ Rule-based Vietnamese emotion detection        │
│                  No LLM calls; outputs confidence scores (Phase 15)
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

### RAGKnowledgeBase (services/rag_knowledge_base.py) — Phase 13

```
RAGKnowledgeBase
├─ __init__(persist_dir) — ChromaDB + sentence-transformers
├─ add_file(filepath: str) → void
│  ├─ Read .txt, .md, .pdf (10 MB max, graceful degradation)
│  ├─ Chunk: 500-char sentences, 50-char overlap
│  └─ Embed + store in ChromaDB
├─ add_documents(docs: list[str]) → void
│  └─ Direct document list embedding
├─ query(prompt: str, top_k: int = 5) → list[str]
│  ├─ Embed query via sentence-transformers
│  └─ Return k nearest chunks from ChromaDB
├─ clear() → void
├─ count() → int
└─ Graceful Degradation:
   └─ If chromadb/sentence-transformers not installed, all ops silently no-op
```

**Integration**: `generator.py` `generate_world()` & `_build_chapter_prompt()` inject RAG context via RAG_CONTEXT_SECTION prompt when `rag_enabled=True`.
**Config**: `rag_enabled`, `rag_persist_dir` in PipelineConfig; controlled via UI/API.
**Cost**: No LLM calls for embedding (uses local sentence-transformers).

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
├─ save_tree(tree: StoryTree, filename="") → str  [PHASE 10]
│  └─ Persist to data/branches/{timestamp}.json
├─ load_tree(path: str) → StoryTree  [PHASE 10]
│  └─ Deserialize from JSON file
├─ list_saved_trees() → list[dict]  [PHASE 10]
│  └─ Return metadata for all saved trees
└─ Constraints:
   ├─ In-memory + local JSON persistence (Phase 10)
   ├─ Max 10 branches per story (MVP)
   └─ User selects active path for Layer 2+
```

**Integration**: Interactive tab UI (branching_tab.py); save/load buttons. Branches exported as JSON metadata + persisted locally.

### WattpadExporter (services/wattpad_exporter.py)

```
WattpadExporter
├─ __init__(username, password) — optional auth for direct upload
├─ export_chapters(chapters, metadata) → list[dict]
│  ├─ Wattpad chapter format: title, parts, author_notes
│  ├─ NovelHD metadata: character bios, worldbuilding, tags
│  ├─ Character/world transcription per chapter
│  ├─ reading_time_min per chapter (words / 200, min 1)  [PHASE 10]
│  └─ character_appendix in metadata  [PHASE 10]
├─ export_zip(output_dir) → str  [PHASE 10]
│  └─ Bundle chapters + character appendix into ZIP
├─ validate_format(chapter) → bool
│  └─ Length limits, character encoding, formatting rules
└─ Local export only (Wattpad API deprecated 2023)
```

**Integration**: Export tab checkbox; outputs ZIP bundle with `.wattpad.json` + `.novelHD.json` metadata (Phase 10).

### TTSAudioGenerator (services/tts_audio_generator.py) — Phase 13 XTTS

```
TTSAudioGenerator
├─ __init__(provider, voice, rate, pitch, character_voice_map)
│  └─ provider: "edge-tts" (default) | "kling" | "xtts" | "none"
├─ generate_chapter_audio(chapter: Chapter, character_name: str = "") → str  # MP3/WAV path
│  ├─ Route to provider:
│  │  ├─ "xtts": POST multipart to Coqui/Replicate + reference audio per character
│  │  ├─ "kling": kling API via character_voice_map lookup
│  │  ├─ "edge-tts": segment synthesis (default)
│  │  └─ "none": skip (return None)
│  └─ Fallback: On XTTS failure → retry edge-tts
├─ character_voice_map: { "CharacterName": "voice_key" } → lookup reference audio
├─ list_voices(lang="vi") → list[str]
└─ data/voices/: Directory for XTTS reference audio clips (character-specific)
```

**Voices**: `vi-VN-HoaiMyNeural`, `vi-VN-NamMinhNeural` (edge-tts); XTTS per-character trained on reference audio (Phase 13)
**Config**: provider, voice, rate, pitch, xtts_api_url, xtts_reference_audio, character_voice_map from PipelineConfig or env
**Phase 13 XTTS Features**:
- Per-character voice cloning via reference audio
- Fallback to edge-tts on API failure
- Multipart POST to Coqui TTS server or Replicate API
- character_voice_map config controls voice per character

### ImageGenerator (services/image_generator.py) — Phase 14 Character Consistency

```
ImageGenerator
├─ __init__(provider, api_key, api_url)
│  └─ provider: "none" | "dalle" | "sd-api" | "seedream" | "replicate"
├─ generate_panel_image(prompt: str, panel_number: int) → Optional[str]
│  ├─ "none" → skip (returns None)
│  ├─ "dalle" → OpenAI images.generate() → download + save
│  ├─ "sd-api" → POST to IMAGE_API_URL with IMAGE_API_KEY
│  ├─ "seedream" → ByteDance Seedream API
│  └─ "replicate" → Replicate IP-Adapter (requires reference images)
├─ generate_with_reference(prompt: str, reference_paths: list[str], filename: str)
│  └─ Routes to seedream/replicate for character-consistent generation
└─ batch_generate(image_prompts: list[str]) → list[Optional[str]]
   └─ ThreadPoolExecutor (max 3 workers)
```

**Provider selection**: `STORYFORGE_IMAGE_PROVIDER` env var
**Credentials**: `IMAGE_API_KEY`, `IMAGE_API_URL`, `SEEDREAM_API_KEY`, `REPLICATE_API_KEY`

### ReplicateIPAdapter (services/replicate_ip_adapter.py) — Phase 14

```
ReplicateIPAdapter
├─ __init__(api_key, model)
│  └─ model: "tencentarc/ip-adapter-faceid-sdxl" (default)
├─ is_configured() → bool
├─ generate(prompt: str, reference_image_path: str, filename: str)
│  ├─ Encode reference image as base64 data URI
│  ├─ POST to Replicate /v1/predictions with prompt + image
│  ├─ Poll for completion (3-sec intervals, 120-sec timeout)
│  ├─ Download result image
│  └─ Return filepath or None on error
└─ Graceful fallback: logs warning if not configured
```

**Config**: `replicate_api_key` in PipelineConfig or `REPLICATE_API_KEY` env var
**Model**: IP-Adapter FaceID-SDXL for character identity consistency

### CharacterVisualProfileStore (services/character_visual_profile.py) — Phase 14

```
CharacterVisualProfileStore
├─ __init__(base_dir: str = "output/characters")
│  └─ Persistent store in base_dir/{safe_char_name}/
├─ save_profile(name: str, appearance_desc: str, reference_image_path: str)
│  ├─ Store profile.json with description + reference image path
│  ├─ Copy reference image into profile directory
│  └─ Log timestamp (ISO format)
├─ load_profile(name: str) → Optional[dict]
│  └─ Returns {"name", "description", "reference_image", "created_at"}
├─ has_profile(name: str) → bool
├─ get_reference_image(name: str) → Optional[str]
│  └─ Returns filesystem path to reference image or None
├─ get_visual_description(name: str) → str
│  └─ Returns frozen description for prompt injection
├─ build_visual_description(character) → str
│  └─ Extract appearance + personality from Character object
├─ list_profiles() → list[dict]
│  └─ All saved profiles with metadata
└─ delete_profile(name: str) → bool
   └─ Remove profile directory + images
```

**Integration**: MediaProducer loads/creates profiles when `enable_character_consistency=True`. ImagePromptGenerator injects frozen descriptions into all panel prompts.
**Storage**: JSON metadata + images in `output/characters/{safe_name}/`

### ImagePromptGenerator Enhanced (services/image_prompt_generator.py) — Phase 14

```
ImagePromptGenerator
├─ generate_from_panel(panel, visual_profiles: dict = {})
│  └─ Inject frozen visual descriptions for each character in visual_profiles
├─ generate_from_chapter(chapter, visual_profiles: dict = {})
│  └─ Build panel prompts with consistent character descriptions
└─ Frozen visual descriptions ensure identical character appearance
   across all generated images in story
```

**Integration**: MediaProducer passes `visual_profiles` dict loaded from CharacterVisualProfileStore

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

### TokenCounter (services/token_counter.py) — Phase 15

```
TokenCounter
├─ estimate_tokens(text: str, model: str) → int
│  └─ Heuristic: ~4 chars per token (fast approximation)
├─ fits_in_context(text: str, model: str, context_limit: int) → bool
│  └─ Returns True if estimated tokens ≤ context_limit
└─ Supported models: gpt-4, gpt-4o, gpt-3.5-turbo, deepseek, others
   └─ Context windows: GPT-4/4o (128k), 3.5-turbo (4k), deepseek (4k)
```

**Integration**: `generator.py` `_format_context()` + `_build_chapter_prompt()` check context fit before LLM call.

### LongContextClient (services/long_context_client.py) — Phase 15

```
LongContextClient
├─ __init__(api_key, model, base_url, timeout_seconds)
├─ generate(prompt: str, max_tokens: int) → str
│  ├─ OpenAI-compatible API call
│  ├─ Retry logic: 3 attempts, exponential backoff
│  └─ JSON mode support if requested
├─ generate_stream(prompt: str) → Iterator[str]
│  └─ Streaming response for real-time feedback
└─ Context window awareness:
   └─ Splits chapters via token_counter if exceeding limit
```

**Config**: `use_long_context` (bool), `long_context_model`, `long_context_base_url`, `long_context_timeout_seconds`
**Integration**: `generator.py` `generate_full_story()` + `continue_story()` route to LongContextClient when `use_long_context=True`.

### EmotionClassifier (services/emotion_classifier.py) — Phase 15

```
EmotionClassifier
├─ classify(text: str) → EmotionResult
│  ├─ Rule-based Vietnamese emotion detection
│  ├─ No LLM calls (local inference only)
│  └─ Returns: emotion, confidence (0.0-1.0)
└─ Emotions: joy, sadness, anger, fear, neutral
```

**Output**: EmotionResult with label + confidence for TTS rate/pitch adjustment.
**Integration**: `tts_audio_generator.py` uses EmotionClassifier to modulate voice characteristics per emotional context.

### DebateOrchestrator (pipeline/agents/debate_orchestrator.py) — Phase 16, Phase 16.5 LLM Upgrade

```
DebateOrchestrator
├─ run_debate(agents, story_draft, layer, round1_reviews) → DebateResult
│  ├─ Round 1: Agents present initial AgentReview scores
│  ├─ Round 2: Agents call LLM-powered debate_response() to challenge/support peers
│  │           Phase 16.5: produces revised_score (0.0-1.0) per DebateEntry
│  ├─ Round 3: Final debate round, consensus vote counted
│  └─ Returns: DebateResult (consensus_score, final_reviews, total_challenges)
└─ Max rounds: configurable via max_debate_rounds
```

**Schemas** (Phase 16.5 updates):
- `DebateStance`: CHALLENGE, SUPPORT, NEUTRAL (enum)
- `DebateEntry`: agent_name, round_number, stance, target_agent, target_issue, reasoning, **revised_score** (new)
- `DebateResult`: consensus_score, final_reviews (list[AgentReview]), total_challenges, debate_skipped, entries

**Phase 16.5 LLM Debate**: DramaCriticAgent and CharacterSpecialistAgent now use LLM-powered debate_response():
- Analyzes peer reviews via LLM (DRAMA_DEBATE, CHARACTER_DEBATE prompts)
- Challenges gently (e.g., drama-reducing suggestions) with evidence
- Produces revised_score to adjust target agent's score if challenge accepted
- Fallback: Rule-based keyword detection if LLM fails

**Integration**: `agent_registry.py` `run_review_cycle()` wires debate into story quality feedback loop when `enable_agent_debate=True`.
**A/B Test**: Threshold changed Phase 16→16.5: 1.5 → **0.10** (0-1 scale) for validated drama delta.

### SmartRevisionService (services/smart_revision.py) — Phase 17

```
SmartRevisionService
├─ __init__(threshold: float = 3.5, max_passes: int = 2)
│  ├─ threshold: 1.0-5.0 scale; chapters with overall < threshold marked as weak
│  └─ max_passes: max revision attempts per chapter (default 2)
│
├─ revise_weak_chapters(enhanced_story, quality_scores, reviews, genre, progress_callback)
│  ├─ Identify weak chapters: ChapterScore.overall < threshold
│  ├─ For each weak chapter:
│  │  ├─ Aggregate agent guidance via _aggregate_review_guidance()
│  │  ├─ Build SMART_REVISE_CHAPTER prompt with issues + suggestions
│  │  └─ [LOOP max_passes]:
│  │     ├─ LLM revise chapter (temp=0.7)
│  │     ├─ Re-score revised chapter
│  │     ├─ Compute delta vs old_score
│  │     └─ Accept if delta >= MIN_IMPROVEMENT_DELTA (+0.3)
│  └─ Return: {revised_count, total_weak, score_deltas: [{chapter, old/new_score, delta, passes}]}
│
└─ _aggregate_review_guidance(chapter_number: int, reviews: list) → (issues, suggestions)
   ├─ Word-boundary regex filter: `\bch(?:ương\s*)?N\b` for chapter-specific guidance
   ├─ Include general issues from low-scoring agents (score < 0.6)
   └─ Cap 5 issues + 5 suggestions per chapter
```

**Config**: `enable_smart_revision` (bool, default False), `smart_revision_threshold` (float 1.0-5.0, default 3.5)
**Validation**: MIN_IMPROVEMENT_DELTA = +0.3 (validated decision threshold)
**Integration**: Runs after Layer 2 agent reviews when `enable_smart_revision=True`
**Benefits**: Automatic weak chapter detection + targeted revision reduces manual QA burden

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
    ├─→ [OPTIONAL] Self-Review (if enable_self_review):
    │   └─→ SelfReviewService.review_chapter() → ChapterReview
    │       └─ If score < self_review_threshold: auto-revise chapter
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
├─ review(output, layer, iteration, prior_reviews) → AgentReview
├─ debate_response(story_draft, layer, own_review, all_reviews) → list[DebateEntry]
├─ _parse_debate_llm_response(result, all_reviews) → list[DebateEntry]  [Phase 16.5 DRY]
├─ _get_chapter_excerpt(story_draft, max_chars) → str  [Phase 16.5 DRY]
├─ _parse_review_json(result, layer, iteration) → AgentReview
└─ Subclasses: CharacterSpecialist, ContinuityChecker, DialogueExpert,
               DramaCritic, EditorInChief

AgentRegistry
├─ discover() → list[BaseAgent]
├─ get_by_name(name) → BaseAgent
├─ run_review_cycle(story_draft, context) → list[AgentReview]
└─ register(agent) → void
```

**Context-aware escalation**: agents detect threshold breaches (drama_intensity, coherence < 2.5)
and escalate feedback priority; orchestrator re-runs affected chapter enhancement.

**Phase 16.5 DRY improvements**: `_parse_debate_llm_response()` and `_get_chapter_excerpt()` shared in BaseAgent to reduce duplication across agent implementations.

### Agent Dependency Graph (AgentDAG) — Phase 13

```
AgentDAG (pipeline/agents/agent_graph.py)
├─ Topological sort via Kahn's algorithm (detects cycles)
├─ Build from registry: agent.depends_on → resolved agent names
├─ get_execution_order() → list[list[BaseAgent]]
│  └─ 4 tiers:
│     Tier 1: CharacterSpecialist (no deps)
│     Tier 2: Continuity, Dialogue, StyleCoordinator, PacingExpert (depend on Tier 1)
│     Tier 3: DramaCritic, DialogueBalance (depend on Tier 1–2)
│     Tier 4: EditorInChief (depends on all)
│
└─ AgentRegistry.run_review_cycle(story_draft, context):
   ├─ If DAG enabled:
   │  └─ Execute each tier in parallel (ThreadPoolExecutor)
   └─ Fallback:
      └─ Flat parallel all agents
```

**Integration**: `agent_registry.py` `run_review_cycle()` uses tiered execution; enhances agent feedback quality by ensuring dependencies are satisfied before dependent agents run.
**Pure Python**: No external dependencies beyond BaseAgent interface.
**Benefits**: Handles unknown agents gracefully; enables future agent extensibility.

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
   ├─ language: "vi" | "en"
   ├─ enable_self_review (bool, default: False)  [PHASE 10]
   ├─ self_review_threshold (float 1.0-5.0, default: 3.0)  [PHASE 10]
   ├─ rag_enabled (bool, default: False)  [PHASE 13]
   ├─ rag_persist_dir (str)  [PHASE 13]
   ├─ xtts_api_url, xtts_reference_audio (str)  [PHASE 13]
   ├─ character_voice_map (dict[str, str])  [PHASE 13]
   ├─ enable_character_consistency (bool, default: False)  [PHASE 14]
   ├─ replicate_api_key (str)  [PHASE 14]
   ├─ character_consistency_provider ("seedream" | "replicate")  [PHASE 14]
   ├─ use_long_context (bool, default: False)  [PHASE 15]
   ├─ long_context_model, long_context_base_url (str)  [PHASE 15]
   ├─ long_context_timeout_seconds (int, default: 120)  [PHASE 15]
   ├─ enable_voice_emotion (bool, default: False)  [PHASE 15]
   ├─ enable_agent_debate (bool, default: False)  [PHASE 16]
   ├─ max_debate_rounds (int, default: 3)  [PHASE 16]
   ├─ enable_smart_revision (bool, default: False)  [PHASE 17]
   └─ smart_revision_threshold (float 1.0-5.0, default: 3.5)  [PHASE 17]

Environment overrides:
├─ STORYFORGE_IMAGE_PROVIDER (none | dalle | sd-api | seedream | replicate)
├─ IMAGE_API_KEY
├─ IMAGE_API_URL
├─ SEEDREAM_API_KEY  [PHASE 14]
├─ SEEDREAM_API_URL  [PHASE 14]
└─ REPLICATE_API_KEY  [PHASE 14]
```

**Phase 10 Addition**: Self-review configuration allows users to opt-in and customize quality thresholds per pipeline run.
**Phase 13 Addition**: RAG and XTTS voice cloning configuration; RAG optional, XTTS provider selection with fallback.
**Phase 14 Addition**: Character consistency configuration; enable visual profile store + choose provider (seedream uses image descriptions, replicate uses reference images).
**Phase 15 Addition**: Long-context LLM configuration (token counter, endpoint, timeout) + emotion-aware TTS voice adjustment.
**Phase 16 Addition**: Multi-agent debate protocol configuration (enable/disable, max rounds).
**Phase 16.5 Addition**: Debate upgraded to LLM-powered; DramaCriticAgent & CharacterSpecialistAgent analyze peer reviews via LLM prompts (DRAMA_DEBATE, CHARACTER_DEBATE); A/B threshold 0.10.
**Phase 17 Addition**: Smart chapter revision configuration (enable/disable, threshold). Weak chapters auto-detected after Layer 2 agent reviews and revised with aggregated guidance.

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

**Architectural Principle**: Modular layers with clear handoffs. Each service is independently testable. Web auth, credits, TTS, and image generation are transparent to core pipeline logic. Phase 9 adds CoT self-review, interactive branching, and expanded export capabilities. Phase 10 adds configuration polish and persistence. Phase 13 adds RAG world-building context, agent dependency graph orchestration, and multi-provider voice synthesis with XTTS v2 cloning. Phase 14 adds character visual profile persistence and multi-provider character-consistent image generation (IP-Adapter + Seedream). Sprint 0 includes 11 critical bug fixes (SQLite concurrency, plot event pruning, word count helpers). Phase 15 adds long-context LLM support (token counter, context window awareness) and emotion-aware voice synthesis. Phase 16 adds multi-agent debate protocol. Phase 16.5 upgrades debate to LLM-powered analysis with revised_score per DebateEntry, DRY helpers in BaseAgent, and A/B threshold 0.10. Phase 17 adds smart chapter revision (auto-detect weak chapters, aggregate agent guidance, validate improvements).

**Last Updated**: 2026-03-25 | **Version**: 2.2 (Phase 17: Smart Chapter Revision)
