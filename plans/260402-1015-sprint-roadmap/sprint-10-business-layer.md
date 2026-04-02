# Sprint 10: Community & Documentation (Open Source)
**Duration:** 1 week | **Owner:** Full Team | **Priority:** HIGH

## Objectives
- Professional README & GitHub presence
- Easy self-hosted setup (one-command install)
- Contributor documentation
- Feedback UI for self-hosted users

## Tasks

### 10.1 README & GitHub Presence [PM + DevOps] — 2 days
- [ ] Rewrite `README.md` for open source:
  - Eye-catching hero banner/logo
  - Clear value proposition (1-2 sentences)
  - Feature highlights with screenshots
  - Quick Start (Docker one-liner + local dev)
  - Architecture overview diagram (Mermaid)
  - Tech stack badges (Python, FastAPI, Alpine.js, Docker)
  - Contributing link, License badge, Star count
- [ ] Create `.github/ISSUE_TEMPLATE/`:
  - `bug_report.yml` — structured bug report form
  - `feature_request.yml` — feature request form
  - `config.yml` — issue chooser
- [ ] Create `.github/PULL_REQUEST_TEMPLATE.md`
- [ ] Create `CONTRIBUTING.md`:
  - Development setup guide
  - Code style & conventions
  - PR process
  - Architecture overview for contributors
- [ ] Create `LICENSE` (MIT or Apache 2.0 — CEO to decide)
- [ ] Create `.github/FUNDING.yml` (optional: GitHub Sponsors, Ko-fi)

### 10.2 One-Command Setup [DevOps] — 1 day
- [ ] Create `scripts/setup.sh`:
  - Check prerequisites (Python 3.10+, pip)
  - Create virtualenv
  - Install dependencies
  - Download font if missing
  - Create data directories
  - Generate .env from .env.example
  - Print "Ready! Run: python app.py"
- [ ] Create `scripts/setup-docker.sh`:
  - Verify Docker + Docker Compose
  - Copy .env.example → .env
  - docker compose up -d
  - Wait for health check
  - Print URL
- [ ] Update `docker-compose.yml` for easy dev start:
  - Works with just `docker compose up` (no config needed)
  - Default to Ollama/free models if no API key

### 10.3 User Guide [Frontend + PM] — 1 day
- [ ] Create `docs/user-guide.md`:
  - Getting Started (first story in 5 minutes)
  - Configuring LLM providers (OpenAI, Gemini, Ollama, OpenRouter)
  - Genre selection guide
  - Understanding quality scores
  - Export formats explained
  - Troubleshooting / FAQ
- [ ] Add in-app help tooltips on complex features
- [ ] Create `docs/self-hosting.md`:
  - Hardware requirements
  - Docker deployment guide
  - Environment variables reference
  - Updating to new versions

### 10.4 Feedback UI [Frontend] — 1 day
- [ ] Add star rating component in story reader view:
  - 1-5 star rating per chapter
  - Optional comment textarea
  - Submit to existing /api/feedback/rate endpoint
- [ ] Add "Report issue" button per chapter
- [ ] Show aggregate ratings on story library cards

## Success Criteria
- [ ] New user can run StoryForge in < 5 minutes (Docker)
- [ ] README has clear setup instructions with zero ambiguity
- [ ] CONTRIBUTING.md covers full dev workflow
- [ ] GitHub issue templates work correctly
- [ ] Feedback ratings visible in story reader
