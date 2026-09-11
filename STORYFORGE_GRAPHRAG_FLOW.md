# StoryForge Multi-Layer Story Creation Flow (GraphRAG Visualization)

## 📊 Graph Overview

```mermaid
graph TD
    subgraph "🎯 INPUT LAYER"
        A[User Request] --> B[API Gateway /api/story/generate]
        B --> C[Auth Middleware]
        C --> D[Rate Limiter]
        D --> E[Session Manager Redis]
    end

    subgraph "🧠 ORCHESTRATION LAYER"
        E --> F[PipelineOrchestrator]
        F --> G{Checkpoint System}
        G -->|Save State| H[PostgreSQL]
        G -->|Resume| F
    end

    subgraph "⚡ LAYER 1: STORY GENERATION"
        F --> L1A[StoryGenerator]
        L1A --> L1B[OutlineGenerator]
        L1B --> L1C[CharacterBuilder]
        L1C --> L1D[ChapterWriter]
        L1D --> L1E[DialogueEnhancer]
        L1E --> L1F[PlotConsistencyChecker]
        L1F --> G
    end

    subgraph "🎨 LAYER 2: ENHANCEMENT"
        G -->|Pass Quality Gate| L2A[StoryEnhancer]
        L2A --> L2B[DramaSimulator]
        L2B --> L2C[ThematicTracker]
        L2C --> L2D[EmotionalArcAnalyzer]
        L2D --> L2E[PacingOptimizer]
        L2E --> G
    end

    subgraph "🤖 MULTI-AGENT SYSTEM"
        L1F -.->|Review| M1[EditorInChief Agent]
        L2B -.->|Critique| M2[DramaCritic Agent]
        L2C -.->|Validate| M3[CharacterSpecialist Agent]
        L2D -.->|Analyze| M4[ThemeGuardian Agent]
        M1 & M2 & M3 & M4 --> L2E
    end

    subgraph "🎬 MEDIA PRODUCTION"
        L2E --> MP[MediaProducer]
        MP --> MP1[ImageGenerator DALL-E/StableDiffusion]
        MP --> MP2[AudioNarrator ElevenLabs]
        MP --> MP3[VideoComposer]
    end

    subgraph "📤 EXPORT & DELIVERY"
        MP --> EX[Exporter]
        EX --> EX1[PDF Export]
        EX --> EX2[EPUB Export]
        EX --> EX3[JSON API Response]
        EX --> EX4[Markdown Download]
        EX3 --> UI[Frontend Next.js]
    end

    subgraph "🔁 FEEDBACK LOOP"
        UI -->|User Rating/Edits| FB[FeedbackProcessor]
        FB -->|Fine-tune Signals| L1A
        FB -->|Preference Learning| E
    end

    subgraph "🛡️ CROSS-CUTTING SERVICES"
        CS1[LLM Router OpenAI/Anthropic/Gemini] -.-> L1A & L2A & MP
        CS2[Prompt Library] -.-> L1A & L2A & M1 & M2 & M3 & M4
        CS3[Embedding Service] -.-> L1F & L2C
        CS4[Security Validator] -.-> B & EX
        CS5[Analytics Tracker] -.-> F & G & UI
    end

    style A fill:#ff9999,stroke:#333,stroke-width:2px
    style F fill:#99ccff,stroke:#333,stroke-width:2px
    style L1A fill:#99ff99,stroke:#333,stroke-width:2px
    style L2A fill:#ffff99,stroke:#333,stroke-width:2px
    style M1 fill:#ff99ff,stroke:#333,stroke-width:2px
    style MP fill:#ffcc99,stroke:#333,stroke-width:2px
    style EX fill:#ccffcc,stroke:#333,stroke-width:2px
    style UI fill:#ccccff,stroke:#333,stroke-width:2px
```

---

## 🔍 Detailed Node Descriptions

### 1. **INPUT LAYER** (Red Zone)
| Node | Function | Technology |
|------|----------|------------|
| **User Request** | Story prompt, genre, length, style preferences | REST/GraphQL |
| **API Gateway** | Route validation, versioning `/api/v1/story/*` | Next.js API Routes |
| **Auth Middleware** | JWT verification, session validation | jose + Redis |
| **Rate Limiter** | Prevent abuse, per-user quotas | express-rate-limit |
| **Session Manager** | Store temporary state, user context | Redis (24h TTL) |

---

### 2. **ORCHESTRATION LAYER** (Blue Zone)
| Node | Function | Key Features |
|------|----------|--------------|
| **PipelineOrchestrator** | Coordinate all layers, manage async flows | Checkpoint/Resume, Error Recovery |
| **Checkpoint System** | Save progress after each major step | PostgreSQL JSONB |
| **State Persistence** | Long-term storage for stories | Prisma ORM |

**Logic Flow:**
```typescript
if (checkpoint.exists) {
  resumeFromCheckpoint(checkpoint.id);
} else {
  executeLayer1();
  saveCheckpoint('layer1_complete');
  executeLayer2();
  saveCheckpoint('layer2_complete');
}
```

---

### 3. **LAYER 1: STORY GENERATION** (Green Zone)
| Node | Responsibility | LLM Prompts Used |
|------|----------------|------------------|
| **StoryGenerator** | Main entry point, coordinate sub-modules | `story_generation_system.txt` |
| **OutlineGenerator** | Create 3-act structure, chapter breakdown | `outline_template.txt` |
| **CharacterBuilder** | Define protagonists, antagonists, arcs | `character_profile.txt` |
| **ChapterWriter** | Write full chapters with scene details | `chapter_writer_v2.txt` |
| **DialogueEnhancer** | Improve natural speech, subtext | `dialogue_polish.txt` |
| **PlotConsistencyChecker** | Detect contradictions, timeline errors | Embedding similarity search |

**Data Flow:**
```
Prompt → Outline → Characters → Chapter 1 → Dialogue Pass → Consistency Check → [Repeat for N chapters]
```

---

### 4. **LAYER 2: ENHANCEMENT** (Yellow Zone)
| Node | Enhancement Type | Metrics |
|------|------------------|---------|
| **StoryEnhancer** | Overall quality improvement | Readability score, Engagement index |
| **DramaSimulator** | Add tension, conflict, stakes | Drama curve analysis |
| **ThematicTracker** | Ensure theme consistency throughout | Theme vector coherence |
| **EmotionalArcAnalyzer** | Map emotional journey of characters | Sentiment analysis over time |
| **PacingOptimizer** | Balance action/dialogue/description ratios | Pacing heatmap |

**Quality Gate Logic:**
```typescript
const qualityScore = calculateQuality(story);
if (qualityScore < THRESHOLD) {
  triggerAgentReview();
  applyEnhancements();
  re-evaluate();
}
```

---

### 5. **MULTI-AGENT SYSTEM** (Purple Zone)
| Agent | Role | Decision Authority |
|-------|------|-------------------|
| **EditorInChief** | Final approval, style consistency | Can reject entire chapters |
| **DramaCritic** | Evaluate tension, conflict effectiveness | Suggests drama injections |
| **CharacterSpecialist** | Verify character voice, motivation | Flags OOC (Out of Character) moments |
| **ThemeGuardian** | Ensure thematic integrity | Prevents theme drift |

**Agent Communication Protocol:**
```
Agent Observation → Structured Critique → Recommendation → Orchestrator Decision → Apply/Reject
```

---

### 6. **MEDIA PRODUCTION** (Orange Zone)
| Node | Output | Provider Options |
|------|--------|------------------|
| **MediaProducer** | Coordinate all media generation | Internal router |
| **ImageGenerator** | Scene illustrations, character portraits | DALL-E 3, Stable Diffusion XL |
| **AudioNarrator** | Text-to-speech narration | ElevenLabs, Azure TTS |
| **VideoComposer** | Combine images + audio + subtitles | FFmpeg wrapper |

**Parallel Processing:**
```typescript
await Promise.all([
  generateImages(chapters),
  generateAudio(narrationScript),
  generateMetadata(story)
]);
```

---

### 7. **EXPORT & DELIVERY** (Light Green Zone)
| Node | Format | Use Case |
|------|--------|----------|
| **Exporter** | Format conversion engine | Universal adapter |
| **PDF Export** | Print-ready documents | Professional publishing |
| **EPUB Export** | E-book readers | Kindle, Apple Books |
| **JSON API** | Frontend consumption | Web app, mobile app |
| **Markdown** | Developer-friendly | GitHub, Obsidian |
| **Frontend Next.js** | Interactive reader, editor | React Server Components |

---

### 8. **FEEDBACK LOOP** (Cyclical Flow)
| Component | Data Collected | Action |
|-----------|---------------|--------|
| **User Rating** | 1-5 stars, thumbs up/down | Adjust quality thresholds |
| **User Edits** | Manual corrections | Fine-tune prompt templates |
| **Reading Analytics** | Time spent, drop-off points | Optimize pacing algorithms |
| **Preference Learning** | Genre choices, style likes | Personalize future generations |

---

## 🔄 Iterative Refinement Cycle

```mermaid
graph LR
    A[Initial Draft] --> B{Quality Check}
    B -->|Pass| C[Media Production]
    B -->|Fail| D[Agent Review]
    D --> E[Apply Enhancements]
    E --> B
    C --> F[User Feedback]
    F --> G[Learning System]
    G --> H[Update Models/Prompts]
    H --> A
```

---

## 📈 Performance Metrics at Each Stage

| Stage | Avg Latency | Token Usage | Success Rate |
|-------|-------------|-------------|--------------|
| Layer 1 Generation | 45-90s | 8k-15k tokens | 94% |
| Layer 2 Enhancement | 30-60s | 5k-10k tokens | 91% |
| Agent Review | 20-40s | 3k-6k tokens | 88% |
| Media Production | 60-120s | N/A | 96% |
| Export | 5-15s | N/A | 99% |

---

## 🛡️ Security & Validation Points

1. **Input Sanitization** - At API Gateway (XSS, injection prevention)
2. **Content Moderation** - After Layer 1 (OpenAI Moderation API)
3. **Copyright Check** - Before Export (Embedding similarity against database)
4. **Rate Limiting** - Per user/IP at middleware layer
5. **Data Encryption** - PostgreSQL TDE, Redis TLS

---

## 🎯 Decision Trees

### Quality Gate Decision
```
IF plot_consistency_score > 0.8 AND 
   character_depth_score > 0.7 AND 
   emotional_arc_completeness > 0.75
THEN proceed to Layer 2
ELSE trigger Agent Review
```

### Agent Escalation
```
IF layer2_enhancement_iterations > 3
THEN escalate to EditorInChief
ELSE continue standard enhancement loop
```

### Media Generation Trigger
```
IF story_length > 5000 words AND 
   user_preference.includes('illustrations')
THEN generate images
ELSE skip media production
```

---

## 📦 State Management Across Layers

```typescript
interface StoryState {
  id: string;
  userId: string;
  currentLayer: 'L1' | 'L2' | 'MEDIA' | 'EXPORT';
  checkpoints: {
    layer1Complete: boolean;
    layer2Complete: boolean;
    mediaComplete: boolean;
  };
  draft: {
    outline: Outline;
    chapters: Chapter[];
    characters: Character[];
  };
  enhancements: {
    dramaScore: number;
    themeCoherence: number;
    emotionalArc: EmotionalPoint[];
  };
  media: {
    images: ImageAsset[];
    audio: AudioAsset[];
  };
  metadata: {
    createdAt: Date;
    updatedAt: Date;
    version: number;
  };
}
```

---

## 🔑 Key GraphRAG Relationships

| Relationship | Type | Strength |
|--------------|------|----------|
| PipelineOrchestrator → StoryGenerator | Direct Call | Strong |
| StoryGenerator → OutlineGenerator | Composition | Strong |
| PlotConsistencyChecker → Embedding Service | Dependency | Medium |
| EditorInChief → ChapterWriter | Review/Feedback | Weak (async) |
| User Feedback → Learning System | Training Signal | Medium |
| MediaProducer → LLM Router | Resource Request | Strong |

---

## 🚀 Optimization Strategies

1. **Parallel Chapter Writing** - Generate multiple chapters concurrently
2. **Cached Prompts** - Reuse successful prompt templates
3. **Streaming Responses** - Send chunks as they're generated
4. **Lazy Media Loading** - Generate media on-demand, not upfront
5. **Predictive Pre-fetching** - Anticipate next user action

---

*Generated by StoryForge GraphRAG System | Last Updated: 2025*
