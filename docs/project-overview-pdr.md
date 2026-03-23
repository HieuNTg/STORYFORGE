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

### Core Features (Phase 1 Complete)

**Layer 1 — Story Generation**
- Character generation with personality, motivation, relationships
- World-building with settings, rules, locations
- Chapter-by-chapter story outline
- Full chapter writing with LLM
- **Phase 1**: Character state tracking (mood, arc, knowledge) + plot event extraction with rolling context window

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

- **OpenAI API** (or OpenClaw): LLM calls (core functionality)
- **Internet connectivity**: Required for API calls
- **config.json**: Configuration file (optional, uses defaults if missing)

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

### Phase 1 Completion (CURRENT)

- [x] CharacterState, PlotEvent, StoryContext models defined
- [x] extract_character_states() method implemented
- [x] extract_plot_events() method implemented
- [x] Rolling context integrated into generate_full_story() loop
- [x] Parallel extraction via ThreadPoolExecutor
- [x] context_window_chapters config parameter added
- [x] LLMClient max_tokens parameter added
- [x] All extraction calls use temp=0.3 + compact max_tokens
- [x] Character state tracking reduces inconsistencies in multi-chapter stories
- [x] Test: 10-chapter story with character tracking (manual validation)

### Phase 2 Roadmap (In Progress)

- [ ] Multi-agent feedback loops (6+ agents)
- [ ] Character consistency validation with examples
- [ ] Drama intensity scoring per chapter
- [ ] Enhanced narrative output with feedback
- [ ] Integration test: Layer 1 → Layer 2 handoff
- [ ] Test: Drama scores correlate with emotional arc

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

**Phase 1** (COMPLETE - 2026-03-23):
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

## Known Limitations & Future Work

### Current Limitations

1. **No user accounts**: All stories are global (no multi-tenancy)
2. **No persistent task queue**: Tasks lost on process restart
3. **Language**: Vietnamese primary (English support TBD)
4. **No UI**: API-only, no web dashboard
5. **Manual review required**: Generated content needs human editing

### Future Enhancements

- User authentication & story ownership
- Background job queue (Celery/RQ)
- Multi-language support
- Web UI for story management
- Export formats (PDF, EPUB, JSON)
- A/B testing for drama parameters

---

**Document Version**: 1.1 (Phase 4 Export)
**Last Updated**: 2026-03-23
**Status**: Phase 1-4 Complete, Phase 2 In Progress
