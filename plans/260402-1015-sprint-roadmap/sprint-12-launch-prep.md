# Sprint 12: Public Release (Open Source)
**Duration:** 1 week | **Owner:** Full Team | **Priority:** CRITICAL

## Objectives
- Public release on GitHub with v1.0.0 tag
- Community launch (Reddit, HN, Discord)
- Operational documentation
- Demo instance for try-before-install

## Tasks

### 12.1 Release Engineering [DevOps] — 2 days
- [ ] Create GitHub Release v1.0.0:
  - Changelog from all sprint commits
  - Pre-built Docker image on GitHub Container Registry (ghcr.io)
  - Release notes with feature highlights
- [ ] Update CI for releases:
  - Auto-publish Docker image on tag push
  - Auto-generate changelog from conventional commits
- [ ] Create `scripts/seed-demo-data.sh`:
  - Pre-generated sample stories (3 genres)
  - Sample configuration for quick demo
- [ ] Setup demo instance:
  - Deploy on fly.io or Railway (free tier)
  - Read-only mode (generate but no save)
  - Link from README

### 12.2 Security Hardening [Security] — 1 day
- [ ] OWASP Top 10 checklist verification
- [ ] Penetration testing on key flows:
  - Prompt injection with adversarial inputs
  - Rate limiter bypass verification
  - File path traversal verification
- [ ] Dependency audit (zero critical/high CVEs)
- [ ] Add SECURITY.md (responsible disclosure policy)

### 12.3 Community Setup [PM] — 1 day
- [ ] Create Discord server or GitHub Discussions:
  - #general, #help, #feature-requests, #show-and-tell
  - Welcome message with links to docs
- [ ] Prepare launch posts:
  - Reddit r/selfhosted, r/LocalLLaMA, r/artificial
  - Hacker News Show HN
  - Vietnamese tech communities
- [ ] Create `CHANGELOG.md` from git history
- [ ] Add "Star History" badge to README

### 12.4 Final Documentation [Full Team] — 2 days
- [ ] Review and polish all docs:
  - README accuracy check
  - User guide completeness
  - Self-hosting guide tested on fresh machine
  - Contributing guide tested by team member
- [ ] Create `docs/api-reference.md`:
  - All API endpoints documented
  - Request/response examples
  - Authentication guide
- [ ] Create architecture diagram (Mermaid in docs/):
  - 3-layer pipeline flow
  - Multi-agent system overview
  - Deployment architecture

## Launch Checklist
- [ ] All CI/CD green
- [ ] Docker image builds and runs on fresh machine
- [ ] README setup instructions tested from scratch
- [ ] Demo instance accessible
- [ ] GitHub Release v1.0.0 created
- [ ] SECURITY.md published
- [ ] CONTRIBUTING.md reviewed
- [ ] LICENSE file present
- [ ] Discord/Discussions ready
- [ ] Launch posts drafted
- [ ] Zero critical bugs
- [ ] All docs up to date

## Success Metrics (Week 1 post-launch)
- GitHub Stars > 100
- Docker pulls > 50
- Issues filed > 10 (engagement signal)
- At least 1 community PR
