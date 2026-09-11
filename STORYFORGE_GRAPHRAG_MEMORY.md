# StoryForge Repository - GraphRAG Memory Map

## 📊 Tổng quan Repository
- **Tổng số files**: ~728 files
- **Ngôn ngữ chính**: TypeScript (Backend), Next.js/React (Frontend)
- **Kiến trúc**: Multi-layer Pipeline với Multi-Agent System
- **Database**: PostgreSQL + Redis (session state, 24h TTL)
- **LLM Providers**: OpenAI, Anthropic, Gemini, OpenRouter

---

## 🏗️ Layer 1: Infrastructure & Middleware
**Vị trí**: `/src/middleware/`, `/src/config/`, `/src/models/`

### Middleware Chain (10 lớp):
1. `errorHandler.ts` - Global error handling
2. `requestLogger.ts` - Request/response logging
3. `corsConfig.ts` - CORS policy
4. `rateLimiter.ts` - Rate limiting
5. `authMiddleware.ts` - JWT authentication
6. `roleBasedAccess.ts` - RBAC authorization
7. `inputSanitizer.ts` - XSS/SQL injection prevention
8. `sessionManager.ts` - Redis session management
9. `cacheMiddleware.ts` - Response caching
10. `apiVersioning.ts` - API version routing

### Config Files:
- `database.config.ts` - PostgreSQL connection pool
- `redis.config.ts` - Redis client setup
- `llm.config.ts` - Multi-provider LLM configuration
- `security.config.ts` - Security policies
- `export.config.ts` - Export format settings

### Core Models:
- `Story.ts` - Story schema (title, genre, chapters, characters)
- `Chapter.ts` - Chapter schema (content, metadata, embeddings)
- `Character.ts` - Character profiles (traits, arcs, relationships)
- `User.ts` - User accounts (roles, preferences, history)
- `PipelineState.ts` - Pipeline execution state
- `Checkpoint.ts` - Save/restore points

---

## 🌐 Layer 2: API Gateway
**Vị trí**: `/src/routes/`, `/src/routes/v1/`

### Unversioned Routes (38 files):
- `health.ts` - Health check endpoint
- `metrics.ts` - System metrics
- `auth/*.ts` - Login, register, refresh, logout
- `user/*.ts` - Profile, preferences, history
- `story/*.ts` - CRUD operations
- `export/*.ts` - PDF, EPUB, DOCX generation
- `media/*.ts` - Image/audio generation
- `search/*.ts` - Full-text search with embeddings

### Versioned Routes v1 (11 files):
- `v1/generate.ts` - Story generation pipeline trigger
- `v1/enhance.ts` - Story enhancement pipeline
- `v1/agents/*.ts` - Agent coordination endpoints
- `v1/pipeline/*.ts` - Pipeline control (start, pause, resume, stop)
- `v1/checkpoint/*.ts` - Checkpoint management
- `v1/export/*.ts` - Advanced export options
- `v1/analytics/*.ts` - Usage analytics

---

## ⚙️ Layer 3: Core Pipeline Engine
**Vị trí**: `/src/pipeline/`

### PipelineOrchestrator (`PipelineOrchestrator.ts`):
- **Chức năng**: Điều phối toàn bộ workflow tạo truyện
- **Features**:
  - Checkpoint system (save/restore tại mọi giai đoạn)
  - Continuation support (tiếp tục từ checkpoint bất kỳ)
  - Parallel execution (chạy song song các tác vụ độc lập)
  - Error recovery (tự động retry với exponential backoff)
  - Progress tracking (real-time progress updates)

### Pipeline Stages:
1. **Input Validation** → Kiểm tra input, sanitize data
2. **Outline Generation** → Tạo cốt truyện tổng thể
3. **Character Development** → Xây dựng nhân vật
4. **Chapter Writing** → Viết từng chapter
5. **Enhancement** → Tăng cường chất lượng (drama, dialogue, pacing)
6. **Media Generation** → Tạo hình ảnh/minh họa
7. **Export Preparation** → Chuẩn bị định dạng xuất
8. **Final Delivery** → Trả kết quả cho user

### Checkpoint System:
- **Lưu trữ**: Redis (nhanh) + PostgreSQL (persistent)
- **TTL**: 24 giờ cho session active
- **Data**: Full pipeline state, partial results, metadata
- **Restore**: Từ bất kỳ checkpoint nào, kể cả sau restart

---

## 📝 Layer 4: Story Generation (Layer 1)
**Vị trí**: `/src/generation/`

### Core Generators (50+ files):

#### Outline Generation:
- `outlineGenerator.ts` - Tạo cốt truyện tổng thể
- `plotStructure.ts` - Plot structures (3-act, hero's journey, etc.)
- `genreTemplates.ts` - Genre-specific templates
- `conflictBuilder.ts` - Build conflict chains

#### Chapter Writing:
- `chapterWriter.ts` - Viết từng chapter
- `sceneBuilder.ts` - Construct individual scenes
- `pacingController.ts` - Control narrative pacing
- `transitionGenerator.ts` - Scene/chapter transitions

#### Character Development:
- `characterGenerator.ts` - Tạo nhân vật
- `characterArc.ts` - Character development arcs
- `relationshipMapper.ts` - Character relationships
- `dialogueStyle.ts` - Individual dialogue styles

#### Dialogue System:
- `dialogueGenerator.ts` - Generate natural dialogue
- `voiceConsistency.ts` - Maintain character voice
- `subtextEngine.ts` - Add subtext to dialogue
- `conflictDialogue.ts` - Conflict-driven dialogue

#### World Building:
- `worldBuilder.ts` - Create story world
- `settingDetails.ts` - Detailed settings
- `cultureGenerator.ts` - Cultures, customs, traditions
- `magicSystem.ts` - Magic/technology systems

---

## 🎨 Layer 5: Enhancement Engine (Layer 2)
**Vị trí**: `/src/enhancement/`

### Enhancers (30+ files):

#### Quality Enhancement:
- `storyEnhancer.ts` - Overall quality improvement
- `prosePolisher.ts` - Improve writing style
- `vocabularyEnhancer.ts` - Richer vocabulary
- `sentenceVariety.ts` - Vary sentence structures

#### Drama & Tension:
- `dramaSimulator.ts` - Simulate dramatic tension
- `conflictAmplifier.ts` - Amplify conflicts
- `stakesBuilder.ts` - Build stakes progressively
- `climaxDesigner.ts` - Design compelling climaxes

#### Thematic Tracking:
- `thematicTracker.ts` - Track themes throughout
- `motifWeaver.ts` - Weave motifs consistently
- `symbolismEngine.ts` - Add symbolic elements
- `themeResolver.ts` - Resolve thematic arcs

#### Emotional Analysis:
- `emotionAnalyzer.ts` - Analyze emotional arcs
- `moodController.ts` - Control mood progression
- `empathyBuilder.ts` - Build reader empathy
- `tensionRelease.ts` - Manage tension/release cycles

#### Consistency Checking:
- `consistencyChecker.ts` - Check story consistency
- `continuityValidator.ts` - Validate continuity
- `logicVerifier.ts` - Verify plot logic
- `factChecker.ts` - Fact-check within story world

---

## 🤖 Layer 6: Multi-Agent System
**Vị trí**: `/src/agents/`

### 14 Chuyên gia AI Agents:

1. **EditorInChief** (`editorInChief.ts`)
   - Phê bình tổng thể, định hướng nghệ thuật
   - Quyết định final quality gate

2. **CharacterSpecialist** (`characterSpecialist.ts`)
   - Expert về phát triển nhân vật
   - Đảm bảo tính nhất quán nhân vật

3. **DramaCritic** (`dramaCritic.ts`)
   - Phân tích kịch tính, xung đột
   - Đề xuất tăng tension

4. **DialogueCoach** (`dialogueCoach.ts`)
   - Huấn luyện đối thoại tự nhiên
   - Voice consistency checking

5. **PlotArchitect** (`plotArchitect.ts`)
   - Thiết kế cấu trúc cốt truyện
   - Plot hole detection

6. **WorldBuilder** (`worldBuilderAgent.ts`)
   - Chuyên gia xây dựng thế giới
   - Consistency trong world-building

7. **PacingExpert** (`pacingExpert.ts`)
   - Tối ưu nhịp độ truyện
   - Balance action/reflection

8. **ThemeAnalyst** (`themeAnalyst.ts`)
   - Phân tích chủ đề sâu
   - Thematic coherence

9. **EmotionProfiler** (`emotionProfiler.ts`)
   - Profiling cảm xúc nhân vật
   - Emotional arc optimization

10. **GenreSpecialist** (`genreSpecialist.ts`)
    - Expert theo thể loại
    - Genre convention adherence

11. **StyleCop** (`styleCop.ts`)
    - Kiểm tra phong cách viết
    - Style guide compliance

12. **ContinuityGuard** (`continuityGuard.ts`)
    - Bảo vệ tính liên tục
    - Catch continuity errors

13. **ReaderAdvocate** (`readerAdvocate.ts`)
    - Đại diện góc nhìn độc giả
    - Engagement optimization

14. **CreativeInnovator** (`creativeInnovator.ts`)
    - Đề xuất ý tưởng sáng tạo
    - Break conventional patterns

### Agent Coordination:
- `agentCoordinator.ts` - Điều phối giữa các agents
- `consensusEngine.ts` - Đạt consensus khi có conflict
- `priorityScheduler.ts` - Ưu tiên tasks cho agents
- `feedbackLoop.ts` - Feedback loops giữa agents

---

## 🔧 Layer 7: Services
**Vị trí**: `/src/services/` (100+ modules)

### LLM Clients:
- `openaiClient.ts` - OpenAI API integration
- `anthropicClient.ts` - Anthropic Claude integration
- `geminiClient.ts` - Google Gemini integration
- `openRouterClient.ts` - OpenRouter multi-model
- `llmRouter.ts` - Intelligent model routing
- `promptOptimizer.ts` - Optimize prompts per model
- `tokenCounter.ts` - Token counting & cost estimation
- `responseParser.ts` - Parse LLM responses

### Authentication & Authorization:
- `jwtService.ts` - JWT token management
- `passwordHasher.ts` - Password hashing (bcrypt)
- `oauthService.ts` - OAuth providers (Google, GitHub)
- `apiKeyService.ts` - API key management
- `permissionChecker.ts` - Permission verification
- `sessionStore.ts` - Session storage (Redis)

### Media Services:
- `imageGenerator.ts` - AI image generation
- `audioGenerator.ts` - AI audio/narration
- `thumbnailCreator.ts` - Thumbnail generation
- `mediaOptimizer.ts` - Media optimization
- `cdnUploader.ts` - CDN upload management

### Export Services:
- `pdfExporter.ts` - PDF generation
- `epubExporter.ts` - EPUB ebook format
- `docxExporter.ts` - Microsoft Word format
- `markdownExporter.ts` - Markdown export
- `htmlExporter.ts` - HTML format
- `jsonExporter.ts` - JSON data export
- `exportTemplateEngine.ts` - Template-based exports

### Search & Embeddings:
- `embeddingGenerator.ts` - Generate text embeddings
- `vectorStore.ts` - Vector database operations
- `semanticSearch.ts` - Semantic search engine
- `fullTextSearch.ts` - Traditional full-text search
- `hybridSearch.ts` - Combine semantic + keyword

### Security Services:
- `inputValidator.ts` - Input validation
- `xssCleaner.ts` - XSS prevention
- `sqlInjector.ts` - SQL injection prevention
- `csrfProtector.ts` - CSRF protection
- `rateLimitStore.ts` - Rate limit storage
- `auditLogger.ts` - Security audit logging

### Prompt Management:
- `promptLibrary.ts` - Centralized prompt library
- `promptTemplater.ts` - Dynamic prompt templating
- `promptVersioning.ts` - Prompt version control
- `promptA/BTester.ts` - A/B testing for prompts
- `promptAnalytics.ts` - Prompt performance analytics

### Caching & Performance:
- `cacheManager.ts` - Multi-level caching
- `queryOptimizer.ts` - Database query optimization
- `connectionPooler.ts` - Connection pooling
- `loadBalancer.ts` - Load balancing
- `performanceMonitor.ts` - Performance monitoring

### Notification Services:
- `emailService.ts` - Email notifications
- `pushNotification.ts` - Push notifications
- `webhookDispatcher.ts` - Webhook management
- `notificationQueue.ts` - Notification queuing

### Analytics & Monitoring:
- `usageTracker.ts` - Usage analytics
- `errorTracker.ts` - Error tracking (Sentry-like)
- `metricCollector.ts` - Metrics collection
- `dashboardDataProvider.ts` - Dashboard data

### Integration Services:
- `webhookReceiver.ts` - Incoming webhooks
- `apiClient.ts` - External API client
- `dataImporter.ts` - Data import utilities
- `dataExporter.ts` - Data export utilities

---

## 🎨 Layer 8: Frontend (Next.js 16 + React 19)
**Vị trí**: `/frontend/`, `/src/components/`

### Component Architecture (20+ folders):

#### Core Components:
- `common/` - Reusable UI components (Button, Input, Modal)
- `layout/` - Layout components (Header, Footer, Sidebar)
- `navigation/` - Navigation components (Menu, Breadcrumb)

#### Story Creation:
- `story/` - Story-related components
  - `StoryEditor.tsx` - Main story editor
  - `ChapterList.tsx` - Chapter management
  - `OutlineBuilder.tsx` - Visual outline builder
  - `CharacterSheet.tsx` - Character profile editor

#### Pipeline Control:
- `pipeline/` - Pipeline control UI
  - `PipelineStatus.tsx` - Real-time status
  - `CheckpointManager.tsx` - Checkpoint UI
  - `ProgressTracker.tsx` - Progress visualization
  - `ErrorRecovery.tsx` - Error recovery UI

#### Agent Interaction:
- `agents/` - Agent interaction components
  - `AgentDashboard.tsx` - Agent overview
  - `AgentFeedback.tsx` - Agent feedback UI
  - `ConsensusView.tsx` - Agent consensus display
  - `AgentChat.tsx` - Chat with agents

#### Enhancement Tools:
- `enhancement/` - Enhancement tools
  - `QualityMeter.tsx` - Quality score display
  - `DramaSlider.tsx` - Adjust drama level
  - `ThemeVisualizer.tsx` - Theme mapping
  - `EmotionGraph.tsx` - Emotional arc graph

#### Export & Sharing:
- `export/` - Export components
  - `ExportWizard.tsx` - Export wizard
  - `FormatSelector.tsx` - Format selection
  - `PreviewPanel.tsx` - Export preview
  - `ShareDialog.tsx` - Sharing options

#### Media Management:
- `media/` - Media components
  - `ImageGallery.tsx` - Image gallery
  - `AudioPlayer.tsx` - Audio narration player
  - `ThumbnailEditor.tsx` - Thumbnail editor
  - `MediaUploader.tsx` - Media upload

#### Search & Discovery:
- `search/` - Search components
  - `SearchBar.tsx` - Global search
  - `FilterPanel.tsx` - Advanced filters
  - `SearchResults.tsx` - Results display
  - `SavedSearches.tsx` - Saved searches

#### User Management:
- `user/` - User components
  - `ProfileEditor.tsx` - Profile editing
  - `PreferencePanel.tsx` - User preferences
  - `HistoryTimeline.tsx` - Creation history
  - `SubscriptionManager.tsx` - Subscription management

#### Analytics & Insights:
- `analytics/` - Analytics components
  - `UsageDashboard.tsx` - Usage stats
  - `PerformanceCharts.tsx` - Performance metrics
  - `QualityTrends.tsx` - Quality trends
  - `CostTracker.tsx` - Cost tracking

#### Settings & Configuration:
- `settings/` - Settings components
  - `GeneralSettings.tsx` - General settings
  - `LLMConfig.tsx` - LLM provider config
  - `SecuritySettings.tsx` - Security settings
  - `IntegrationSettings.tsx` - Third-party integrations

#### Real-time Features:
- `realtime/` - Real-time components
  - `LiveCollaboration.tsx` - Real-time collaboration
  - `PresenceIndicator.tsx` - User presence
  - `SyncStatus.tsx` - Sync status
  - `ConflictResolver.tsx` - Conflict resolution

#### Accessibility:
- `a11y/` - Accessibility components
  - `ScreenReaderSupport.tsx` - Screen reader support
  - `KeyboardNavigation.tsx` - Keyboard navigation
  - `ColorContrast.tsx` - Color contrast tools
  - `FocusManager.tsx` - Focus management

#### Testing & Debugging:
- `debug/` - Debug components
  - `DevTools.tsx` - Developer tools
  - `LogViewer.tsx` - Log viewer
  - `StateInspector.tsx` - State inspector
  - `PerformanceProfiler.tsx` - Performance profiler

### State Management:
- `store/` - Redux/Zustand store
  - `storySlice.ts` - Story state
  - `userSlice.ts` - User state
  - `pipelineSlice.ts` - Pipeline state
  - `settingsSlice.ts` - Settings state

### Hooks:
- `hooks/` - Custom React hooks
  - `useStory.ts` - Story operations
  - `usePipeline.ts` - Pipeline control
  - `useAgent.ts` - Agent interactions
  - `useExport.ts` - Export operations
  - `useRealtime.ts` - Real-time features

### Pages:
- `pages/` or `app/` (Next.js 16 App Router)
  - `dashboard/` - Main dashboard
  - `create/` - Story creation flow
  - `edit/[id]/` - Story editor
  - `library/` - Story library
  - `profile/` - User profile
  - `settings/` - Settings page
  - `analytics/` - Analytics dashboard

---

## 🔄 Data Flow (End-to-End)

```
User Input (Frontend)
    ↓
API Gateway (Routes)
    ↓
Middleware Chain (10 layers)
    ↓
PipelineOrchestrator
    ↓
┌─────────────────────────────────────┐
│  Stage 1: Input Validation          │
│  Stage 2: Outline Generation        │
│  Stage 3: Character Development     │
│  Stage 4: Chapter Writing           │ ← Checkpoint saved
│  Stage 5: Enhancement (L2)          │
│  Stage 6: Media Generation          │
│  Stage 7: Export Preparation        │
│  Stage 8: Final Delivery            │
└─────────────────────────────────────┘
    ↓
Multi-Agent Review (14 agents)
    ↓
Consensus & Quality Gate
    ↓
Response → Frontend
```

### Checkpoint Flow:
```
Pipeline State → Serialize → Redis (fast) + PostgreSQL (persistent)
    ↓
[TTL: 24h for active sessions]
    ↓
Restore: Deserialize → Resume from exact state
```

### Agent Coordination Flow:
```
Story Draft → Distribute to 14 Agents
    ↓
Each Agent: Analyze → Provide Feedback
    ↓
Consensus Engine: Aggregate → Resolve Conflicts
    ↓
EditorInChief: Final Decision
    ↓
Apply Changes → Updated Draft
```

---

## 🔑 Key Architectural Patterns

### 1. **Pipeline Pattern**
- Sequential stages với checkpoint tại mỗi stage
- Support pause/resume/rollback
- Parallel execution cho independent tasks

### 2. **Multi-Agent Pattern**
- Specialized agents với domain expertise
- Consensus-based decision making
- Feedback loops для continuous improvement

### 3. **CQRS Pattern** (Command Query Responsibility Segregation)
- Separate read/write models
- Optimized queries vs commands
- Event sourcing for state changes

### 4. **Repository Pattern**
- Abstraction over data access
- Easy switching between databases
- Testable data layer

### 5. **Strategy Pattern**
- Pluggable LLM providers
- Swappable export formats
- Configurable enhancement strategies

### 6. **Observer Pattern**
- Real-time progress updates
- Event-driven architecture
- Pub/sub for agent communication

### 7. **Circuit Breaker Pattern**
- Fault tolerance for external APIs
- Automatic retry with backoff
- Fallback mechanisms

### 8. **Saga Pattern**
- Distributed transaction management
- Compensation for failed steps
- Consistency across services

---

## 📈 Scalability & Performance

### Horizontal Scaling:
- Stateless API servers (scale out easily)
- Redis cluster for session state
- PostgreSQL read replicas
- CDN for media assets

### Caching Strategy:
- L1: In-memory cache (frequently accessed data)
- L2: Redis cache (session state, partial results)
- L3: Database query cache
- L4: CDN cache (static assets, media)

### Performance Optimizations:
- Connection pooling (database, LLM APIs)
- Batch processing (embeddings, exports)
- Lazy loading (large stories, media)
- Compression (responses, assets)
- Minification (frontend bundles)

### Monitoring:
- Real-time metrics (Prometheus/Grafana)
- Distributed tracing (Jaeger/Zipkin)
- Log aggregation (ELK stack)
- Alerting (PagerDuty/Slack)

---

## 🔒 Security Architecture

### Authentication:
- JWT tokens (access + refresh)
- OAuth 2.0 (Google, GitHub)
- API keys for programmatic access
- Session management (Redis, 24h TTL)

### Authorization:
- Role-based access control (RBAC)
- Resource-level permissions
- Fine-grained access policies
- Audit logging for all actions

### Data Protection:
- Encryption at rest (AES-256)
- Encryption in transit (TLS 1.3)
- Input sanitization (XSS, SQL injection)
- CSRF protection
- Rate limiting (DDoS prevention)

### Compliance:
- GDPR compliance (data privacy)
- Data retention policies
- Right to be forgotten
- Data portability

---

## 🧪 Testing Strategy

### Unit Tests:
- Jest for backend logic
- React Testing Library for components
- Mock LLM responses
- Mock external services

### Integration Tests:
- API endpoint testing
- Database integration
- Redis integration
- LLM provider integration

### End-to-End Tests:
- Cypress/Playwright for frontend flows
- Full pipeline testing
- Multi-agent coordination testing
- Export functionality testing

### Performance Tests:
- Load testing (k6, Artillery)
- Stress testing
- Soak testing (long-running pipelines)
- Spike testing (sudden traffic)

### Security Tests:
- OWASP ZAP for vulnerability scanning
- Penetration testing
- Dependency scanning (Snyk, Dependabot)
- Code analysis (SonarQube)

---

## 🚀 Deployment Architecture

### Environments:
- Development (local, feature branches)
- Staging (pre-production, QA)
- Production (multi-region)

### CI/CD Pipeline:
- GitHub Actions / GitLab CI
- Automated testing
- Container build (Docker)
- Kubernetes deployment
- Blue-green deployments
- Canary releases

### Infrastructure:
- Kubernetes cluster (EKS/GKE/AKS)
- Managed PostgreSQL (RDS/Cloud SQL)
- Managed Redis (ElastiCache/Memorystore)
- Object storage (S3/GCS) for media
- CDN (CloudFront/Cloudflare)

### Disaster Recovery:
- Multi-AZ deployment
- Automated backups (daily + point-in-time)
- Failover mechanisms
- Recovery time objective (RTO): < 1 hour
- Recovery point objective (RPO): < 15 minutes

---

## 📚 Knowledge Graph Entities

### Core Entities:
- **Story**: Title, Genre, Chapters[], Characters[], Themes[]
- **Chapter**: Content, Metadata, Embeddings[], Checkpoints[]
- **Character**: Name, Traits, Arc, Relationships[], DialogueStyle
- **User**: Profile, Preferences, History[], Subscriptions
- **Pipeline**: Stages[], State, Checkpoints[], Metrics
- **Agent**: Role, Expertise, Feedback[], Decisions[]
- **Checkpoint**: Timestamp, State, Metadata, RestorePoint

### Relationships:
- User → creates → Story
- Story → contains → Chapter[]
- Story → features → Character[]
- Pipeline → processes → Story
- Agent → reviews → Story/Chapter
- Checkpoint → belongs to → Pipeline
- Embedding → represents → Chapter/Character

### Operations:
- Create, Read, Update, Delete (CRUD) trên tất cả entities
- Generate (Story, Chapter, Character, Dialogue)
- Enhance (Quality, Drama, Theme, Emotion)
- Export (PDF, EPUB, DOCX, Markdown)
- Search (Semantic, Full-text, Hybrid)
- Checkpoint (Save, Restore, List, Delete)

---

## 🎯 Use Cases Supported

### For Writers:
- AI-assisted story creation
- Character development tools
- Plot structure guidance
- Real-time quality feedback
- Export to multiple formats

### For Editors:
- Multi-agent review system
- Consistency checking
- Quality scoring
- Collaborative editing
- Version comparison

### For Publishers:
- Bulk story generation
- Format conversion
- Quality assurance
- Analytics & insights
- Distribution preparation

### For Developers:
- Extensible plugin system
- Custom agent creation
- API integration
- White-label solutions
- Self-hosting options

---

## 🔮 Future Roadmap (Potential Extensions)

### Planned Features:
- Multi-language support (i18n)
- Voice narration (TTS integration)
- Interactive storytelling (choose-your-path)
- Collaboration tools (real-time co-writing)
- Marketplace (buy/sell story assets)
- Mobile apps (iOS/Android)
- VR/AR story experiences
- Blockchain integration (NFT stories)

### Technical Improvements:
- Fine-tuned custom LLM models
- Better long-context handling
- Improved agent reasoning
- Enhanced personalization
- Faster export generation
- Better mobile responsiveness
- Offline mode support

---

## 📞 Quick Reference

### Key Directories:
```
/src
  /middleware      - 10 middleware layers
  /config          - Configuration files
  /models          - Database models
  /routes          - API routes (unversioned + v1)
  /pipeline        - Core pipeline engine
  /generation      - Story generation (L1)
  /enhancement     - Enhancement engine (L2)
  /agents          - 14 AI agents
  /services        - 100+ service modules
  /components      - Frontend components

/frontend
  /components      - React components (20+ folders)
  /pages or /app   - Next.js pages
  /store           - State management
  /hooks           - Custom hooks
```

### Key Commands:
```bash
# Development
npm run dev              # Start dev server
npm run test             # Run tests
npm run lint             # Lint code
npm run type-check       # TypeScript check

# Production
npm run build            # Build for production
npm run start            # Start production server
npm run migrate          # Run database migrations
npm run seed             # Seed database

# Docker
docker-compose up        # Start all services
docker-compose build     # Build containers
docker-compose down      # Stop services
```

### Environment Variables:
```bash
# Database
DATABASE_URL=postgresql://...
REDIS_URL=redis://...

# LLM Providers
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
GEMINI_API_KEY=...
OPENROUTER_API_KEY=...

# Security
JWT_SECRET=...
ENCRYPTION_KEY=...

# Frontend
NEXT_PUBLIC_API_URL=...
NEXT_PUBLIC_APP_URL=...
```

---

*GraphRAG Memory Map created for StoryForge Repository*
*Last updated: 2025*
*Total files mapped: ~728*
