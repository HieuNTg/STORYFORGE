# Novel Auto Pipeline — Product Development Requirements (PDR)

## Project Overview

**Novel Auto** is an automated three-layer pipeline for generating dramatic multimedia content (novels, enhanced narratives, video storyboards) from story concepts using AI-powered language models.

**Vision**: Democratize drama-driven storytelling by automating character consistency, plot depth, and visual adaptation across formats.

## Product Definition

### What Is Novel Auto?

A modular AI pipeline that transforms a genre + story idea into:
1. **Layer 1**: Complete novel draft (10-50 chapters) with rolling character state tracking
2. **Layer 2**: Drama-enhanced narrative via multi-agent feedback loops
3. **Layer 3**: Video storyboards with shot-level metadata

### Core Features

**StoryForge Phase 1 — Browser Web Auth + Zero-Config Onboarding (NEW)**
- Native browser-based web authentication (Chrome CDP + Playwright)
- Automatic credential capture from DeepSeek login flow
- 13 pre-configured story templates (zero-config quick start)
- Template selector with genre-based filtering
- "Tao ngay" quick-start button for instant generation
- Support for free DeepSeek web API (no API key required)

**Layer 1 — Story Generation**
- Character generation with personality, motivation, relationships
- World-building with settings, rules, locations
- Chapter-by-chapter story outline
- Full chapter writing with LLM
- **Character State Tracking**: mood, arc, knowledge extraction per chapter
- **Plot Event Extraction**: major story events + character involvement
- **Rolling Context Window**: keep last N chapters + capped plot events (50 max)

**Layer 2 — Drama Enhancement** (In Progress)
- Multi-agent simulation (6+ agents)
- Character consistency verification
- Plot hole detection
- Dialogue quality scoring
- Drama intensity feedback loops

**Layer 3 — Video Storyboarding** (Planned)
- Scene-level breakdown
- Camera direction generation
- Shot scheduling per chapter

### User Personas

| Persona | Use Case | Needs |
|---------|----------|-------|
| **Author** | Generate novel drafts quickly | Character consistency, plot coherence, narrative depth |
| **Screenwriter** | Adapt stories to video | Scene breakdown, visual metadata, shot planning |
| **Publisher** | Quality content at scale | Consistency checks, drama intensity control, fast iteration |
| **Creator** | Multi-format content | Unified story management, platform-agnostic output |

## Functional Requirements

### StoryForge Phase 1: Browser Web Auth + Zero-Config Onboarding (NEW)

**Req-SF1.1**: Browser-based credential capture
- Input: User launches Chrome, logs into DeepSeek
- Process: Playwright intercepts HTTP Authorization header + cookies
- Output: Credentials stored in data/auth_profiles.json
- Acceptance Criteria:
  - Chrome launches with CDP on port 9222
  - Login flow completes without blocking
  - Credentials auto-recovered on app restart

**Req-SF1.2**: Story template library
- Input: Genre selection (Tiên Hiệp, Huyền Huyễn, Ngôn Tình, etc.)
- Output: 13 pre-configured templates with story idea + chapter/character counts
- Acceptance Criteria:
  - Templates load from data/templates/story_templates.json
  - Genre dropdown filters available templates
  - Each template has title, idea, recommended num_chapters, num_characters

**Req-SF1.3**: Template-driven quick start
- Input: User selects template + clicks "Tao ngay"
- Process: Auto-fill form fields from template, trigger generation
- Output: Full pipeline execution with template parameters
- Acceptance Criteria:
  - Form fields pre-populated from template
  - Generation starts immediately (no additional input needed)
  - User can still customize before clicking "Tao ngay"

**Req-SF1.4**: Dual-backend LLM routing
- Input: backend_type config ("api" or "web")
- Process: LLMClient routes to appropriate backend
- Output: Generated text via selected backend
- Acceptance Criteria:
  - "api" backend: OpenAI-compatible (requires api_key)
  - "web" backend: DeepSeek via browser auth (free, no key)
  - Routing transparent to pipeline layers
  - Both backends support retry + caching

### Layer 1: Story Generation

**Req-1.1**: Generate story characters from genre + idea
- Input: Genre, story idea, character count
- Output: List of characters with name, role, personality, background, motivation
- Acceptance Criteria:
  - All characters have required fields
  - Characters are genre-appropriate
  - Relationships between characters are logical

**Req-1.2**: Generate world/setting from genre + characters
- Input: Genre, characters
- Output: WorldSetting with name, description, rules, locations, era
- Acceptance Criteria:
  - World supports all character types
  - Rules are internally consistent
  - Locations enable story progression

**Req-1.3**: Generate chapter outlines (full story structure)
- Input: Title, characters, world, num_chapters, story idea
- Output: Synopsis + list of ChapterOutline with title, summary, key_events, emotional_arc
- Acceptance Criteria:
  - Outline spans all chapters with clear progression
  - Key events drive character development
  - Emotional arcs build to climax

**Req-1.4**: Write full novel chapter-by-chapter
- Input: Title, genre, style, characters, world, chapter outline
- Output: Chapter with written content, word count, summary
- Acceptance Criteria:
  - Word count within ±10% of target
  - Writing style consistent with config
  - Chapter advances plot and character development

**Req-1.5** (Phase 1): Extract character state from chapter
- Input: Chapter content, character list
- Output: CharacterState per character (mood, arc_position, knowledge, relationships, last_action)
- Acceptance Criteria:
  - All tracked characters have state
  - State reflects chapter events accurately
  - State is usable for next chapter context

**Req-1.6** (Phase 1): Extract plot events from chapter
- Input: Chapter content, chapter number
- Output: PlotEvent list (event, characters_involved)
- Acceptance Criteria:
  - Only major story events captured
  - Events are uniquely identifiable
  - Character involvement is accurate

**Req-1.7** (Phase 1): Maintain rolling context window
- Input: Chapter states, plot events, summaries
- Process: Keep last N chapter summaries, merge character states, cap plot events at 50
- Output: StoryContext for next chapter write
- Acceptance Criteria:
  - Context passed to next chapter reduces inconsistencies
  - Window size configurable (context_window_chapters)
  - Memory usage bounded (no unbounded growth)

**Req-1.8**: Generate story drafts end-to-end
- Input: Title, genre, idea, num_chapters, num_characters
- Output: StoryDraft with characters, world, outlines, chapters, character_states, plot_events
- Acceptance Criteria:
  - All chapters written and coherent
  - Final character_states and plot_events exported for Layer 2
  - Generation time < 30 minutes for 10 chapters

### Layer 2: Drama Enhancement

**Req-2.1**: Multi-agent feedback simulation
- Input: StoryDraft + character_states (from Layer 1)
- Output: Enhanced narrative with agent feedback metadata
- Acceptance Criteria:
  - All 6+ agents provide feedback
  - Feedback addresses character consistency, plot coherence, dialogue quality
  - Narrative is updated based on highest-priority feedback

**Req-2.2**: Character consistency validation
- Input: Full story + character_states
- Output: Consistency report (conflicts, contradictions)
- Acceptance Criteria:
  - Flags inconsistent actions/dialogue
  - Suggests character arc corrections
  - No false positives on intended character growth

**Req-2.3**: Drama intensity scoring
- Input: Narrative
- Output: Intensity score per chapter (1-10), adjustments
- Acceptance Criteria:
  - Scores align with configured drama_intensity
  - Pacing is optimized for emotional impact
  - Climax chapters have highest intensity

### Layer 3: Video Storyboarding

**Req-3.1**: Generate scene breakdown
- Input: Chapter + enhanced narrative
- Output: Scene list with location, characters, duration
- Acceptance Criteria:
  - All chapters divided into scenes
  - Scene count matches shots_per_chapter config
  - Scenes support visual adaptation

**Req-3.2**: Generate shot-level metadata
- Input: Scene
- Output: Shot with camera direction, angle, action, dialogue
- Acceptance Criteria:
  - Shots are visually distinct
  - Camera directions are cinematically sound
  - All dialogue attributed correctly

### Phase 2: UI Polish & Progress UX (NEW)

**Req-2.4**: Real-time progress bar with layer detection
- Input: Log messages from pipeline execution
- Output: HTML progress bar showing Layer 1 → Layer 2 → Layer 3 states
- Process: _detect_layer() parses messages, updates progress_bar HTML
- Acceptance Criteria:
  - 3-segment progress bar with idle/active/done states
  - Layer detection robust to Vietnamese diacritics (NFD normalization)
  - Progress updates in real-time via progress_callback
  - CSS animations: pulse on active, green on done

**Req-2.5**: Status badge state machine
- Input: Pipeline execution state
- Output: Status badge HTML (idle/running/done/error)
- Acceptance Criteria:
  - "San sang" (idle) → "Dang chay" (running) → "Hoan thanh" (done)
  - Error state on exception with red color
  - Pulse animation on running state
  - XSS-safe HTML rendering via _html.escape()

**Req-2.6**: Output tabs consolidation (6 → 4)
- Consolidate output display from 6 tabs to 4 tabs
- Acceptance Criteria:
  - Tab 1 "Truyen": Layer 1 draft + Layer 2 enhanced (split sections)
  - Tab 2 "Mo Phong": Simulation results
  - Tab 3 "Video": Storyboard & script
  - Tab 4 "Danh Gia": Agent reviews + quality scores
  - Reduced UI clutter, faster navigation

**Req-2.7**: Collapsed detail log accordion
- Detail log hidden behind "Chi tiet tien trinh" accordion (collapsed by default)
- Acceptance Criteria:
  - Progress log visible only on user expand
  - Live preview always visible
  - Saves screen space in default UI

**Req-2.8**: Mobile responsive CSS
- Responsive design for touch devices (max-width: 768px)
- Acceptance Criteria:
  - Flexbox adjustments for mobile layout
  - Progress bar font reduced on small screens
  - Touch-friendly badge and button sizing

**Req-2.9**: Resume pipeline with streaming
- resume_from_checkpoint() accepts progress_callback parameter
- Acceptance Criteria:
  - Same signature as run_pipeline() for consistency
  - Streams progress updates via callback
  - DRY principle maintained (both methods use same streaming)

### Phase 5: Story Quality Metrics (NEW)

**Req-5.1**: LLM-as-judge quality scoring per chapter
- Input: Chapter content + previous chapter context
- Output: ChapterScore (coherence, character_consistency, drama, writing_quality on 1-5 scale)
- Acceptance Criteria:
  - All 4 dimensions scored
  - Scores clamped to 1-5 range
  - Long chapters excerpted (head+tail) to fit budget
  - Uses "cheap" model tier + temp=0.2 for determinism

**Req-5.2**: Aggregate story quality scores
- Input: list[ChapterScore] + layer marker
- Output: StoryScore (avg per dimension, overall, weakest_chapter)
- Acceptance Criteria:
  - Overall = mean of 4 dimension averages
  - Identifies lowest-scoring chapter
  - Scoring layer recorded (1 or 2)

**Req-5.3**: Parallel scoring with sequential context
- Process: Score chapters in parallel, but build context sequentially
- Acceptance Criteria:
  - Max 3 workers (ThreadPoolExecutor)
  - Each chapter receives prev chapter content as context
  - No LLM call overhead > 30% of chapter write time

**Req-5.4**: Integration at Layer 1 & Layer 2
- After Layer 1 story generation: Score draft chapters
- After Layer 2 enhancement: Score enhanced chapters + compute delta
- Logging: Overall score, weakest chapter, improvement (Layer 2 vs Layer 1)
- Acceptance Criteria:
  - Scoring gracefully skips on failure (non-blocking)
  - Scores appended to PipelineOutput.quality_scores[]
  - UI displays quality tab with metrics

**Req-5.5**: UI quality metrics tab
- New "Chat Luong" tab displaying quality_output Markdown
- Checkbox: "Cham diem tu dong" to toggle scoring on/off
- Display: Per-layer scores with weakest chapter highlights
- Acceptance Criteria:
  - Tab visible when scoring completes
  - Checkbox controls orchestrator enable_scoring parameter
  - Output updates with pipeline progress

## Non-Functional Requirements

### Performance

**Req-P1**: Story generation latency
- 10 chapters: < 30 minutes (with parallel extraction)
- Each chapter: < 3 minutes (write + extraction)
- Extraction: < 10 seconds per type (summary, states, events)
- Metrics: Measure via progress callbacks

**Req-P2**: API response time
- POST /api/generate-story: Return task_id within 2 seconds
- GET /api/status: Return status within 1 second
- All endpoints: p99 < 5 seconds

**Req-P3**: Memory efficiency
- Layer 1: < 500MB RAM for 50-chapter story
- Context window: Bounded (rolling summaries, capped plot events)
- No memory leaks on repeated requests

### Reliability

**Req-R1**: LLM resilience
- Retry failed calls up to 3 times with exponential backoff
- Fallback from OpenClaw to OpenAI API on failure
- Cache results to avoid redundant calls (TTL: 7 days)
- All failures log warnings (non-blocking)

**Req-R2**: Data integrity
- Pydantic schema validation on all model instantiation
- Invalid entries logged + skipped (not crashed)
- Final output always includes all chapters (even if some extractionsail)

**Req-R3**: Configuration management
- Config load from data/config.json with sensible defaults
- Changes persist to disk
- Thread-safe singleton access

### Scalability

**Req-S1**: Concurrent requests
- Support 3+ concurrent story generation tasks
- Config: max_parallel_workers=3
- Thread-pool executor for extraction parallelism

**Req-S2**: Codebase extensibility
- Layer 2 agents discoverable via AgentRegistry
- New agents inherit from BaseAgent (interface)
- Prompts centralized in services/prompts.py (easy to update)

### Security & Privacy

**Req-Sec1**: API authentication (Planned)
- Token-based auth for /api endpoints
- Rate limiting per user

**Req-Sec2**: Sensitive data handling
- LLM API keys stored in config (not in code)
- Cache results don't contain secrets
- Logs scrubbed of API keys

### Maintainability

**Req-M1**: Code organization
- Modular layers (layer1, layer2, layer3)
- Clear separation of concerns (services, models, agents)
- Documented with docstrings + architecture docs

**Req-M2**: Configuration
- All tunable parameters in config (temperature, max_tokens, context_window)
- Avoid magic numbers in code
- Document all config options

## Technical Constraints & Dependencies

### Technology Stack

| Component | Technology | Version | Rationale |
|-----------|-----------|---------|-----------|
| Language | Python | 3.10+ | LLM ecosystem maturity |
| Web | Flask | Latest | Lightweight, minimal setup |
| Data Model | Pydantic | v2 | Type-safe validation |
| LLM API | OpenAI SDK | Compatible | Widely available |
| Cache | SQLite | Built-in | No external DB needed |
| Async | ThreadPoolExecutor | Built-in | No async/await complexity |

### External Dependencies

- **LLM Backend** (choose one):
  - OpenAI API-compatible endpoint (requires api_key)
  - DeepSeek web API (free, requires Chrome for browser auth)
- **Chrome/Chromium**: Required for web auth (browser_auth.py)
- **Internet connectivity**: Required for API/web calls
- **Playwright**: Automated browser control for credential capture
- **Requests library**: HTTP client for web backend

### Configuration Constraints

| Parameter | Min | Default | Max | Notes |
|-----------|-----|---------|-----|-------|
| num_chapters | 1 | 10 | 100 | More chapters = longer generation |
| words_per_chapter | 500 | 2000 | 5000 | Affects LLM token usage |
| context_window_chapters | 1 | 2 | 5 | More context = higher token cost |
| temperature (gen) | 0.0 | 0.8 | 1.0 | Higher = more creative |
| temperature (extract) | 0.0 | 0.3 | 0.5 | Lower = more consistent |
| max_tokens | 500 | 4096 | 8000 | Higher = longer output |
| num_agents | 3 | 6 | 10 | More agents = higher cost |

## Acceptance Criteria

### StoryForge Phase 1 Completion (NEW - COMPLETE)

- [x] BrowserAuth class with Chrome CDP launcher
- [x] Playwright-based credential interception
- [x] DeepSeekWebClient with PoW challenge solver
- [x] browser_auth.py service (capture, store, retrieve credentials)
- [x] deepseek_web_client.py service (API calls + streaming)
- [x] LLMClient dual-backend routing ("api" vs "web")
- [x] 13 story templates in data/templates/story_templates.json
- [x] Template loader (_load_templates()) in app.py
- [x] Template selector dropdown with genre filtering
- [x] "Tao ngay" quick-start button
- [x] Web auth UI tab (launch Chrome, capture, clear credentials)
- [x] Config updates: backend_type, web_auth_provider
- [x] Requirements.txt: playwright, requests added
- [x] OpenClaw references removed (replaced with web auth)
- [x] Tests: manual validation of web auth flow + template selection

### Character State Tracking (Phase 1 - Original)

- [x] CharacterState, PlotEvent, StoryContext models
- [x] extract_character_states() method
- [x] extract_plot_events() method
- [x] Rolling context integration
- [x] Parallel extraction via ThreadPoolExecutor
- [x] context_window_chapters config
- [x] Character consistency improved in multi-chapter stories

### Phase 5 Completion (NEW - COMPLETE)

- [x] ChapterScore model with 4 dimensions (coherence, character_consistency, drama, writing_quality)
- [x] StoryScore aggregate model with layer marker
- [x] QualityScorer service with score_chapter() & score_story() methods
- [x] Parallel scoring (max 3 workers, ThreadPoolExecutor)
- [x] Sequential context building (each chapter sees prev chapter)
- [x] Long chapter truncation (head 2600 + tail 1400 chars)
- [x] Cheap model tier + low temperature (0.2)
- [x] Layer 1 scoring integration (after story generation)
- [x] Layer 2 scoring integration (after enhancement + delta logging)
- [x] UI: "Chat Luong" tab with quality_output Markdown
- [x] UI: "Cham diem tu dong" checkbox (enable_scoring)
- [x] 9-element output tuple (added quality field)
- [x] All 77 test cases passed
- [x] No breaking changes to Phase 1-4

### Phase 2 Completion (UI Polish & Progress UX - COMPLETE)

- [x] _progress_html() function with 3-segment progress bar
- [x] _detect_layer() with Vietnamese diacritics support (NFD normalization)
- [x] _strip_diacritics() utility function
- [x] Status badges with 4 states (idle/running/done/error)
- [x] CSS animations (pulse, transitions, mobile-responsive)
- [x] Output tabs consolidation (6 → 4)
- [x] Collapsed detail log accordion
- [x] Mobile responsive design (@media queries)
- [x] XSS-safe HTML rendering (_html.escape())
- [x] resume_from_checkpoint() with progress_callback parameter
- [x] DRY principle: resume matches run_pipeline() signature
- [x] 60+ comprehensive unit tests (test_phase2_ui.py)
- [x] No breaking changes to Phase 1, 5

### Phase 3 Roadmap (Future)

- [ ] Scene breakdown generation
- [ ] Shot-level storyboard generation
- [ ] Camera direction prompts
- [ ] Integration test: Layer 2 → Layer 3 handoff
- [ ] Video metadata output format

### Phase 4 Roadmap (Export & Download)

- [x] File export returning list of paths (export_output)
- [x] ZIP bundling functionality (export_zip)
- [x] gr.File widget for multi-file download in UI
- [x] Export format selection (TXT, Markdown, JSON)
- [x] Markdown export with story metadata
- [ ] PDF export support
- [ ] EPUB export support

## Success Metrics

### Layer 1 (Phase 1)

**Metric**: Character state consistency
- Measure: Manual review of 10-chapter story for character contradictions
- Success: < 2 contradictions (vs. 5-10 without tracking)
- Tool: Use EXTRACT_CHARACTER_STATE to identify state changes

**Metric**: Generation speed
- Measure: Time to generate 10-chapter story
- Success: < 30 minutes (with 3 parallel workers)
- Includes: all extraction + writing time

**Metric**: Context window effectiveness
- Measure: References to past events in later chapters
- Success: 70%+ of chapters reference previous chapters accurately
- Tool: Manual audit of cross-chapter coherence

### Phase 5 (Story Quality Metrics)

**Metric**: Scoring speed
- Measure: Time to score N chapters (Layer 1 + Layer 2)
- Success: < 10% overhead vs chapter writing time
- Tool: Log delta from orchestrator

**Metric**: Score consistency
- Measure: Same chapter scored twice = same result (±0.1)
- Success: 95%+ consistency (low temperature = deterministic)
- Tool: Unit test with fixed content

**Metric**: Coherence detection
- Measure: Can identify low-coherence vs high-coherence chapters
- Success: Low chapters score < 2.5, high chapters > 3.5
- Tool: Manual audit of sample outputs

**Metric**: Character consistency detection
- Measure: Detects OOC (out-of-character) behavior
- Success: Flags inconsistent actions < 3 chapters after established trait
- Tool: Manual review of sample chapters

### Layer 2 (Phase 2)

**Metric**: Agent feedback quality
- Measure: Feedback addresses specific story elements
- Success: 80%+ feedback is actionable + specific
- Tool: Manual review of feedback output

**Metric**: Drama intensity accuracy
- Measure: Intensity scores vs. human annotation
- Success: Correlation > 0.7 with human-marked intensity
- Tool: Correlation analysis

## Roadmap & Timeline

**StoryForge Phase 1** (COMPLETE - 2026-03-23):
- Browser web authentication (Chrome CDP + Playwright)
- DeepSeek free API client with PoW solver
- 13 story templates + zero-config onboarding
- Dual-backend LLM routing (API vs web)
- Template-driven quick start UI

**Character State Tracking Phase 1** (COMPLETE - 2026-03-23):
- Character state tracking with rolling context
- Plot event extraction
- Parallel extraction in generation loop

**Phase 2** (In Progress):
- Multi-agent feedback simulation
- Consistency validation
- Drama intensity scoring

**Phase 3** (Planned Q2-Q3 2026):
- Video storyboarding
- Shot scheduling
- Full end-to-end testing

**Phase 4** (COMPLETE - 2026-03-23):
- File export with multi-format support (TXT, Markdown, JSON)
- ZIP bundling for batch downloads
- gr.File UI widget integration
- Story metadata in Markdown export

**Phase 5** (COMPLETE - 2026-03-23):
- LLM-as-judge quality metrics
- Coherence, character consistency, drama, writing quality scoring
- Parallel scoring (max 3 workers)
- Layer 1 & Layer 2 integration

## Known Limitations & Future Work

### Current Limitations

1. **Web auth credentials**: Stored in plain JSON (data/auth_profiles.json); production should encrypt
2. **Chrome dependency**: Web backend requires Chrome/Chromium (not available in headless servers)
3. **Single session**: Web auth captures one provider at a time (no multi-provider support yet)
4. **Language**: Vietnamese primary (English support TBD)
5. **No user accounts**: All stories are global (no multi-tenancy)
6. **Manual review required**: Generated content needs human editing

### Future Enhancements

- User authentication & story ownership
- Background job queue (Celery/RQ)
- Multi-language support
- Web UI for story management
- Export formats (PDF, EPUB, JSON)
- A/B testing for drama parameters

---

**Document Version**: 1.2 (StoryForge Phase 1: Web Auth + Templates)
**Last Updated**: 2026-03-23
**Status**: StoryForge Phase 1 Complete, Character State Phase 1 Complete, Phase 4-5 Complete, Phase 2 In Progress
