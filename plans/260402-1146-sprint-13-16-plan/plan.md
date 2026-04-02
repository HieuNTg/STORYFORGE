# Sprint 13–16 Plan: StoryForge Post-Launch Hardening & Growth

**Created**: 2026-04-02 | **Author**: CTO | **Version**: 1.0
**Horizon**: 4 weeks (Sprint 13 = Week of 2026-04-06)
**Baseline**: 12 sprints complete, 1327 tests, v2.5 shipped
**Tech stack**: Python/FastAPI backend, Alpine.js + Tailwind frontend, PostgreSQL + Redis, Docker Compose

---

## Team Capacity Assumptions

| Member | Role | Capacity (hrs/week) | Notes |
|--------|------|---------------------|-------|
| Minh | Backend Lead | 40 | Owns core pipeline & API |
| Đức | Security | 32 | Part-time; also reviews BE PRs |
| Tùng | DevOps | 36 | Owns infra, CI/CD, Docker |
| Linh | Frontend Lead | 40 | Owns web/ directory |
| Hà | QA | 32 | Part-time; pairs with Linh/Minh |
| Khoa | AI/ML | 40 | Owns pipeline AI services |
| Trang | Product/Marketing | 24 | Part-time; delivers static assets |
| Phúc | Tech Research | 20 | Part-time; POC only, no production |

**Sprint velocity assumption**: S = 2–4h, M = 4–8h, L = 8–16h per task.
**Total team capacity**: ~264 hrs/week across all roles.

---

## Sprint 13: Production Hardening

**Dates**: 2026-04-06 – 2026-04-10 (Week 1)
**Sprint Goal**: Eliminate dependency bloat and security gaps so the production stack is lean, reproducible, and observable.

### Task Table

| Task ID | Owner | Description | Priority | Effort | Dependencies |
|---------|-------|-------------|----------|--------|--------------|
| BE-1 | Minh | Remove `gradio` from requirements.txt; audit and prune its ~50 transitive deps; verify all imports removed from codebase | P0 | M | None |
| SEC-4 | Đức | Pin ALL remaining dependencies with exact versions (`==`) in requirements.txt; generate requirements.lock via `pip-compile`; add lock file to CI | P0 | S | BE-1 (do after Gradio removal to avoid locking dead deps) |
| BE-2 | Minh | Audit all `ThreadPoolExecutor` usage across pipeline/ and services/; produce written migration plan (async vs thread pool per call site); no code changes this sprint | P1 | M | None |
| SEC-1 | Đức | Document JWT rotation policy (expiry windows, refresh strategy); implement in-memory token revocation list backed by Redis SET with TTL | P1 | M | None |
| BE-4 | Minh | Configure SQLAlchemy connection pool for production: `pool_size`, `max_overflow`, `pool_timeout`, `pool_recycle`; document settings in `.env.example` | P1 | S | None |
| OPS-1 | Tùng | Implement `GET /health/deep` endpoint: checks DB connectivity (SQLAlchemy ping), Redis PING, LLM provider reachability (HEAD or fast completion); returns structured JSON with per-service status and latency | P0 | M | None |
| OPS-2 | Tùng | Create Grafana dashboard config (JSON provisioning file) with panels: request rate, p50/p99 latency, error rate, active pipeline runs; add Prometheus alert rules for error rate >5% and p99 >10s | P1 | M | OPS-1 (metrics endpoints must exist) |
| OPS-3 | Tùng | Write PostgreSQL backup cron script using `pg_dump`; store compressed dumps to `data/backups/` with 7-day retention; add to Docker Compose as a scheduled service or host cron entry; document restore procedure | P1 | S | None |

### Acceptance Criteria

- [ ] `pip install -r requirements.txt` installs without Gradio or any of its UI framework deps
- [ ] `pip-compile` lock file committed; CI fails if lock is out of sync with requirements.txt
- [ ] All dependencies pinned with `==` (no `>=`, `~=`, `^`)
- [ ] `GET /api/health/deep` returns HTTP 200 with JSON `{"db": "ok", "redis": "ok", "llm": "ok"}` (or per-service errors)
- [ ] Token revocation: a revoked JWT returns HTTP 401 on subsequent requests without server restart
- [ ] SQLAlchemy pool config documented in `.env.example` with production-recommended values
- [ ] Grafana dashboard JSON imports cleanly; at least 4 panels visible
- [ ] Prometheus alert rules file passes `promtool check rules`
- [ ] `pg_dump` script tested end-to-end; restore tested against a fresh DB instance
- [ ] BE-2 async audit document committed to `docs/async-migration-plan.md`

### Risks & Blockers

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Gradio removal breaks Gradio-specific SSE or progress callbacks | Medium | High | Audit `progress_tracker.py` and `audio_routes.py` before removal; replace any Gradio-specific APIs with FastAPI equivalents |
| Pinning deps breaks dev environments with conflicting system packages | Low | Medium | Test `pip install` in clean Docker image as part of CI |
| Redis not provisioned in all environments for JWT revocation list | Medium | Medium | Fall back to in-process dict with warning log if Redis unavailable |
| LLM health check adds latency/cost if it fires a real completion | Low | Low | Use a minimal HEAD request or a cached no-op prompt; cap at 1s timeout |

---

## Sprint 14: Quality & Testing

**Dates**: 2026-04-13 – 2026-04-17 (Week 2)
**Sprint Goal**: Establish a frontend test baseline, real-database integration tests, and token cost visibility so the team ships with measurable confidence.

### Task Table

| Task ID | Owner | Description | Priority | Effort | Dependencies |
|---------|-------|-------------|----------|--------|--------------|
| FE-1 | Linh | Set up Vitest for frontend JS testing (`web/js/`); write initial unit tests covering `api-client.js` (all public methods) and `app.js` (state transitions, form submission, error paths) | P0 | M | None |
| QA-1 | Hà | Integrate Vitest into GitHub Actions CI: install step, `npm test` command, fail-fast on error; cache `node_modules`; report coverage to CI summary | P0 | S | FE-1 |
| FE-3 | Linh | Optimise Vite build config: enable code splitting (dynamic `import()`), configure `manualChunks` for vendor libs, enable tree shaking, set `build.minify = 'terser'`; target <200 KB initial JS bundle | P1 | M | None |
| QA-2 | Hà | Add real-database integration tests using SQLite (CI) and PostgreSQL (staging): cover user creation, auth flows, credit transactions, story checkpoint persistence; use pytest fixtures with test DB teardown | P0 | L | Sprint 13 BE-4 (pool config must be stable) |
| QA-3 | Hà | Raise coverage target to 80% for `services/auth.py`, `services/user_store.py`, credit service, and export service; add missing tests until threshold met; enforce with `--cov-fail-under=80` in CI | P1 | M | QA-2 |
| AI-2 | Khoa | Implement token cost tracking middleware: intercept every LLM call, record `{story_id, layer, model, prompt_tokens, completion_tokens, cost_usd}` to a new `token_usage` table (or append-only JSONL log); expose `GET /api/v1/usage/{story_id}` | P1 | M | None |
| AI-4 | Khoa | Add budget cap for agent debate: configurable `max_tokens_per_debate_round` (default 8000); accumulate token count per round; abort debate early and log warning if cap exceeded; add config field to `PipelineConfig` | P1 | S | AI-2 (reuse cost-tracking hook) |
| AI-1 (design) | Khoa | Design eval pipeline specification: define human eval dataset format (JSON schema), automated metrics (BLEU, narrative coherence score, character consistency score), data collection flow; deliver `docs/eval-pipeline-spec.md` | P1 | M | None |

### Acceptance Criteria

- [ ] `npm test` runs in CI and fails the build on test failures
- [ ] Vitest covers `api-client.js` and `app.js` with >= 60% line coverage at initial baseline
- [ ] Vite production bundle initial JS <= 200 KB (measured via `npx bundlesize` or Vite bundle report)
- [ ] Integration tests run against SQLite in CI and pass green
- [ ] Integration tests run against PostgreSQL in staging pipeline and pass green
- [ ] Auth, credits, export modules each hit 80% coverage (`--cov-fail-under=80`)
- [ ] `GET /api/v1/usage/{story_id}` returns token + cost breakdown per layer
- [ ] Debate aborts (with log entry) when token cap is reached; no unhandled exception
- [ ] `docs/eval-pipeline-spec.md` committed and reviewed by team
- [ ] New `max_tokens_per_debate_round` config field has safe default; backward compatible

### Risks & Blockers

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Alpine.js components hard to unit-test outside browser DOM | High | Medium | Use `jsdom` environment in Vitest; mock Alpine store; start with pure-function helpers in `api-client.js` |
| Token cost tracking adds latency to every LLM call | Low | Medium | Use async write (fire-and-forget to DB); never block the LLM response path |
| Integration tests flaky due to DB state leakage between tests | Medium | Medium | Use transaction rollback fixtures; seed minimal data per test |
| Coverage target 80% may be unreachable for legacy code in one sprint | Medium | Low | Scope to 4 named modules only; do not apply globally |

---

## Sprint 15: AI Quality & UX Polish

**Dates**: 2026-04-20 – 2026-04-24 (Week 3)
**Sprint Goal**: Deliver a working AI eval pipeline, persistent vector storage, and a polished mobile-accessible UI while closing security gaps before public launch.

### Task Table

| Task ID | Owner | Description | Priority | Effort | Dependencies |
|---------|-------|-------------|----------|--------|--------------|
| AI-1 (impl) | Khoa | Implement eval pipeline v1: automated scoring runner (BLEU + coherence metrics from spec), human eval collection endpoint (`POST /api/v1/eval/submit`), eval result storage, summary report generation | P0 | L | Sprint 14 AI-1 design spec |
| AI-3 | Khoa | Configure ChromaDB persistent storage: set `persist_directory` in RAG config (`data/rag/`), call `client.persist()` after write operations, add startup check that verifies collection survives restart; update `.env.example` | P1 | S | None |
| AI-5 | Khoa | Research Vietnamese NLP emotion classifier upgrade: evaluate `underthesea`, `PhoBERT-sentiment`, and OpenAI embedding-based classification; deliver comparison report `docs/emotion-classifier-options.md`; no production change yet | P1 | M | None |
| AI-6 | Khoa | Implement intelligent model fallback: extend `LLMConfig.fallback_models` with per-model `max_latency_ms` and `max_cost_per_1k` thresholds; fallback logic checks latency (via ping) and cost before selecting model; add `fallback_reason` to response metadata | P1 | L | Sprint 13 SEC-4 (stable deps) |
| FE-4 | Linh | Mobile responsiveness audit: test all pages at 375px, 414px, 768px breakpoints using Chrome DevTools; fix layout breaks in story form, branch reader, audio player; ensure tap targets >= 44px; no JS changes required | P0 | M | None |
| FE-5 | Linh | WCAG 2.1 AA accessibility audit: run axe-core against all pages; fix critical (level A) and serious (level AA) violations: color contrast, missing alt text, form labels, keyboard navigation, ARIA roles on modal dialogs | P1 | M | FE-4 |
| FE-2 | Linh | Evaluate TypeScript migration ROI: measure current JS codebase size (LOC, files), estimate migration effort (file-by-file), assess team TS proficiency, compare bug rates in typed vs untyped modules; deliver `docs/typescript-migration-roi.md` (report only, no migration) | P2 | S | None |
| SEC-2 | Đức | Design RBAC matrix: define 4 roles (viewer, creator, admin, superadmin) with permission sets (read/write/delete stories, manage users, access analytics, configure pipeline); deliver `docs/rbac-matrix.md`; no code implementation this sprint | P1 | S | None |
| SEC-3 | Đức | Adversarial prompt injection testing: create a test corpus of >= 20 injection attempts in Vietnamese and English (jailbreaks, role-play escapes, delimiter attacks, indirect injection via story content); run against current `block_on_injection` middleware; document results in `docs/prompt-injection-test-report.md` | P1 | M | None |
| SEC-5 | Đức | Production CORS config audit: review current `middleware/` CORS settings; verify `allow_origins` is not `["*"]` in production; enforce specific origin allowlist via `STORYFORGE_CORS_ORIGINS` env var; update nginx CORS headers to match; document in `.env.example` | P0 | S | None |

### Acceptance Criteria

- [ ] Eval pipeline: automated scoring runs on a 5-story test set and produces a JSON report; human eval endpoint accepts and stores submissions
- [ ] ChromaDB persists across container restart (verified in Docker Compose test)
- [ ] `docs/emotion-classifier-options.md` committed with benchmark comparison table
- [ ] Model fallback triggers on simulated high-latency; `fallback_reason` present in API response
- [ ] All pages render without horizontal scroll at 375px viewport
- [ ] All tap targets >= 44px (verified via axe-core or manual audit)
- [ ] Zero axe-core critical/serious violations on home, generate, and branch-reader pages
- [ ] `docs/typescript-migration-roi.md` committed
- [ ] `docs/rbac-matrix.md` committed with permission table
- [ ] Prompt injection test corpus >= 20 cases; results documented; regression test added to CI for known-blocked patterns
- [ ] `STORYFORGE_CORS_ORIGINS` env var respected in production Docker config; `["*"]` removed

### Risks & Blockers

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| ChromaDB persistent client API changed in recent versions | Medium | Low | Pin chromadb version in Sprint 13 SEC-4; read migration guide |
| Eval metrics (BLEU etc.) require NLTK/sacrebleu dep not currently in requirements | Medium | Medium | Add to requirements.txt in this sprint with pinned version; small package, low risk |
| FE-4 mobile fixes may require Alpine.js component refactoring | Medium | Medium | Scope to CSS/Tailwind fixes only; escalate to next sprint if JS logic must change |
| AI-6 latency-aware fallback adds pre-call ping overhead | Medium | Medium | Cache ping result for 30s; skip ping if last ping was recent |

---

## Sprint 16: Go-to-Market & Community

**Dates**: 2026-04-27 – 2026-05-01 (Week 4)
**Sprint Goal**: Launch public-facing presence, one-click deploy options, and community channels so external users can discover, deploy, and contribute to StoryForge.

### Task Table

| Task ID | Owner | Description | Priority | Effort | Dependencies |
|---------|-------|-------------|----------|--------|--------------|
| MKT-1 | Trang | Build landing page as a static site (separate from the app): feature showcase (3-layer pipeline, voice mode, branch reader), screenshots, CTA buttons (Deploy, GitHub, Discord); deploy to GitHub Pages or Vercel | P0 | L | None |
| MKT-2 | Trang | Create one-click deploy buttons for Railway, Render, and Vercel: write platform-specific config files (`railway.toml`, `render.yaml`, `vercel.json`); test deploy flow end-to-end on each platform; add badge links to README | P0 | L | Sprint 13 SEC-4 (stable requirements.txt required for deploy configs) |
| MKT-3 | Trang | Generate 3–5 sample stories using the production pipeline (different genres: Tiên Hiệp, Ngôn Tình, Trinh Thám); export as HTML/PDF; host as a gallery page linked from landing page | P1 | M | MKT-1 |
| MKT-4 | Trang | Set up Discord server: create channels (#announcements, #general, #bug-reports, #feature-requests, #showcase); write and post community guidelines and code of conduct; set up GitHub-to-Discord webhook for release notifications | P1 | S | None |
| MKT-5 | Trang | Write Vietnamese README (`README.vi.md`) and `docs/getting-started-vi.md`: cover installation, config, first story run, common troubleshooting; mirror structure of English docs | P1 | M | None |
| TR-3 | Phúc | MCP integration POC: expose StoryForge pipeline as MCP tools (generate_story, get_checkpoint, list_genres); implement in a standalone `mcp_server.py`; test with Claude Desktop or another MCP client; deliver `docs/mcp-poc-report.md` | P1 | L | None |
| TR-6 | Phúc | WebSocket POC for branch reader: replace current polling/SSE with a WebSocket connection for real-time branch continuation streaming; implement in a feature branch; benchmark latency vs SSE; deliver `docs/websocket-branch-poc.md` | P2 | M | None |
| TR-1 | Phúc | Long-context model optimisation research: profile current RAG usage (query frequency, token savings, latency overhead); identify which pipeline stages could skip RAG with a 128k+ context window; deliver `docs/long-context-rag-optimization.md` | P2 | M | None |
| OPS-4 | Tùng | Set up centralised logging: deploy Grafana Loki (or equivalent) in Docker Compose; configure all services to forward structured JSON logs; add log retention policy (14 days); add "Logs" panel to Grafana dashboard from Sprint 13 OPS-2 | P1 | M | Sprint 13 OPS-2 |
| OPS-5 | Tùng | Staging/production config parity audit: diff all env vars, Docker Compose service definitions, nginx configs, and volume mounts between staging and production stacks; document gaps in `docs/config-parity-audit.md`; resolve critical differences | P1 | S | None |
| OPS-7 | Tùng | Configure Certbot auto-renewal: add `certbot renew --quiet` to host cron (or Docker Compose service); test dry-run renewal; document certificate paths and renewal schedule in `docs/ssl-renewal.md` | P1 | S | None |

### Acceptance Criteria

- [ ] Landing page live at a public URL; loads in < 3s on 4G (Lighthouse performance >= 80)
- [ ] One-click deploy tested and working on at least 2 of 3 platforms (Railway, Render, Vercel)
- [ ] 3 sample stories accessible from gallery page; each shows title, genre, and excerpt
- [ ] Discord server live with all 5 channels; community guidelines pinned in #general
- [ ] `README.vi.md` committed and linked from main `README.md`
- [ ] MCP POC: at least 2 tools callable from an MCP client; report committed
- [ ] WebSocket POC: latency benchmark documented; recommendation on whether to proceed
- [ ] Long-context optimisation report committed with concrete recommendation
- [ ] Loki (or equivalent) receiving logs from all Docker Compose services
- [ ] Config parity audit document committed; zero critical discrepancies between staging and prod
- [ ] Certbot dry-run renewal exits 0; cron entry confirmed in host or Docker Compose

### Risks & Blockers

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Railway/Render deploy requires secrets not in repo — onboarding friction | High | Medium | Document required env vars with descriptions in deploy config; use platform secret store |
| MCP protocol version mismatch with Claude Desktop | Medium | Low | Target MCP spec 1.0; document tested client version in POC report |
| Loki resource usage on small VPS exceeds available RAM | Medium | Medium | Use promtail + remote Loki cloud (Grafana free tier) if self-hosted RAM is < 4 GB |
| Trang part-time (24 hrs) — MKT-1 + MKT-2 together are 2×L tasks | High | Medium | Prioritize MKT-2 (deploy buttons) if time runs short; MKT-1 can ship with minimal design |
| Sample story generation (MKT-3) may surface quality issues before public launch | Low | High | Review generated stories internally before publishing; run through quality gate |

---

## Backlog (Not Scheduled — Low Priority)

These items are captured but will not be started until Sprint 17+. Re-prioritise at Sprint 16 retrospective.

| Task ID | Owner | Description | Estimated Effort | Rationale for Deferral |
|---------|-------|-------------|------------------|------------------------|
| BE-5 | Minh | Migrate ThreadPoolExecutor hot paths to async/await (from BE-2 plan) | XL | High-risk refactor; needs full async audit first |
| BE-6 | Minh | GraphQL API layer (alternative to REST for frontend queries) | XL | YAGNI until client complexity demands it |
| FE-6 | Linh | TypeScript migration (full codebase) | XL | Deferred pending ROI report from FE-2 |
| AI-7 | Khoa | Fine-tune a custom Vietnamese narrative LLM on StoryForge output | XL | Requires eval pipeline (AI-1) and sufficient training data first |
| OPS-6 | Tùng | Kubernetes migration (replace Docker Compose) | XL | Premature; Docker Compose sufficient at current scale |
| QA-6 | Hà | Mutation testing with `mutmut` | M | Nice-to-have; standard test suite should come first |
| SEC-6 | Đức | Implement RBAC in code (from SEC-2 design) | L | Design must be approved before implementation |
| SEC-7 | Đức | Full security penetration test (external vendor) | L | Budget approval required |
| MKT-6 | Trang | Paid social media campaign | M | Requires community baseline first |
| MKT-7 | Trang | Product Hunt launch | M | Requires landing page + sample gallery live first (MKT-1, MKT-3) |

---

## Success Metrics

### Sprint 13 Success Metrics
| Metric | Target |
|--------|--------|
| requirements.txt install size (MB) | Reduce by >= 40% from Gradio removal |
| `pip install` time in CI (cold) | < 90 seconds |
| Unpinned dependencies | 0 |
| `/api/health/deep` response time | < 500 ms |
| Token revocation round-trip latency | < 50 ms (Redis SET + lookup) |
| Backup script test: restore to empty DB | Passes without error |

### Sprint 14 Success Metrics
| Metric | Target |
|--------|--------|
| Frontend test coverage (api-client + app.js) | >= 60% line coverage |
| Integration test suite green in CI | 100% pass rate |
| Vite initial JS bundle size | < 200 KB |
| Token cost tracking availability | 100% of LLM calls recorded |
| Module coverage (auth, credits, export) | >= 80% |

### Sprint 15 Success Metrics
| Metric | Target |
|--------|--------|
| Eval pipeline automated score variance | < 0.2 std dev across 5 identical runs |
| ChromaDB persistence verified | Survives 3× container restart |
| Mobile layout issues at 375px | 0 horizontal overflow |
| axe-core critical/serious violations | 0 on 3 core pages |
| CORS misconfiguration (wildcard in prod) | 0 |
| Prompt injection blocked rate | >= 90% of test corpus blocked |

### Sprint 16 Success Metrics
| Metric | Target |
|--------|--------|
| Landing page Lighthouse performance score | >= 80 |
| Successful deploy platforms | >= 2 of 3 |
| Discord members (first week) | >= 20 |
| Log ingestion latency (event to Loki) | < 10 seconds |
| Config parity gaps resolved | 100% of critical gaps |

---

## Cross-Sprint Dependencies

```
Sprint 13 SEC-4 (pinned deps)
  → Sprint 14 QA-2 (stable DB config)
  → Sprint 15 AI-6 (stable deps for new packages)
  → Sprint 16 MKT-2 (stable requirements.txt for deploy configs)

Sprint 13 OPS-1 (deep health endpoint)
  → Sprint 13 OPS-2 (Grafana/Prometheus needs metrics)
  → Sprint 16 OPS-4 (Loki extends Grafana dashboard)

Sprint 14 AI-1 (eval spec)
  → Sprint 15 AI-1 (eval implementation)

Sprint 14 AI-2 (token tracking)
  → Sprint 14 AI-4 (budget cap reuses tracking hook)

Sprint 15 SEC-2 (RBAC design)
  → Backlog SEC-6 (RBAC implementation)

Sprint 15 FE-2 (TS migration ROI)
  → Backlog FE-6 (TypeScript migration)

Sprint 16 MKT-1 (landing page)
  → Sprint 16 MKT-3 (sample gallery links from landing page)
  → Backlog MKT-7 (Product Hunt needs landing page)
```

---

## Definition of Done (All Sprints)

1. Code reviewed and approved by at least 1 other team member (PR merge)
2. All existing tests still passing (`pytest` green, Vitest green from Sprint 14 onward)
3. New functionality has tests (unit or integration as appropriate)
4. Documentation updated: inline docstrings + relevant `docs/` file
5. No new `pip install` unpinned deps introduced
6. Feature flagged off by default if experimental (backward-compatible config field)
7. Deployed to staging and smoke-tested before production merge

---

*Next review: Sprint 13 retrospective — 2026-04-10*
*Document owner: CTO | Plan directory: plans/260402-1146-sprint-13-16-plan/*
