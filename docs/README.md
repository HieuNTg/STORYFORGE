# StoryForge Documentation

Welcome to the StoryForge documentation. Start here to understand the project, architecture, and deployment.

## Quick Navigation

### For New Developers
1. **[Codebase Summary](./codebase-summary.md)** — Overview of the 376-file codebase, key services, and API endpoints
2. **[System Architecture](./system-architecture.md)** — How the 3-layer pipeline works, service organization, and P3 sprint improvements
3. **[Code Standards](./code-standards.md)** — Naming conventions, design patterns, security best practices

### For DevOps / Operators
1. **[Deployment Guide](./deployment-production.md)** — Production setup, Redis authentication, horizontal scaling, monitoring
2. **[System Architecture](./system-architecture.md)** — High-availability considerations, performance optimization

### For Product / Project Managers
1. **[Project Overview & PDR](./project-overview-pdr.md)** — Vision, features, P3 sprint deliverables, requirements matrix

### For Users Planning v4.0 Migration
1. **[Deprecations & Migration Guide](./deprecations-v4-migration.md)** — Browser auth removal timeline, migration path

## File Guide

| Document | Lines | Audience | Purpose |
|----------|-------|----------|---------|
| [codebase-summary.md](./codebase-summary.md) | 357 | Developers | Repository overview, service details, API endpoints |
| [system-architecture.md](./system-architecture.md) | 276 | Architects, DevOps | System design, P3 changes, HA considerations |
| [code-standards.md](./code-standards.md) | 483 | Developers | Style guide, patterns, security checklist |
| [deployment-production.md](./deployment-production.md) | 144 | DevOps, SRE | Production setup, scaling, monitoring |
| [deprecations-v4-migration.md](./deprecations-v4-migration.md) | 131 | Users, Developers | Browser auth removal, migration guide |
| [project-overview-pdr.md](./project-overview-pdr.md) | 208 | PMs, Stakeholders | Vision, requirements, acceptance criteria |

## Architecture Decision Records (ADRs)

| ADR | Topic | Sprint |
|-----|-------|--------|
| [0001](./adr/0001-l1-handoff-envelope.md) | Typed `L1Handoff` envelope and `NegotiatedChapterContract` collapse `getattr(..., None) or []` blind spots into one validated chokepoint. | Sprint 1 |
| [0002](./adr/0002-semantic-verification.md) | Local CPU embeddings (multilingual MiniLM) + spaCy NER replace keyword payoff / structural / outline checks; LLM critic removed from critical path. | Sprint 2 |
| [0003](./adr/0003-generation-hardening-drama-ceiling.md) | `drama_ceiling` derived on the contract and injected into the chapter writer prompt; speaker-anchored voice revert; async D3 contract; batched structural rewriter. | Sprint 3 |

## Sprint Plans

Each sprint dir contains `README.md`, `phases.md`, `schema.md`, `risks.md`.

- [`plans/260503-2317-l1-l2-handoff-envelope/`](../plans/260503-2317-l1-l2-handoff-envelope/README.md) — Sprint 1: handoff envelope, contract unification, diagnostics endpoint.
- [`plans/260504-1213-semantic-verification/`](../plans/260504-1213-semantic-verification/README.md) — Sprint 2: embedding service, NER, objective outline metrics.
- [`plans/260504-1356-generation-hardening/`](../plans/260504-1356-generation-hardening/README.md) — Sprint 3: drama ceiling wiring, speaker-anchored revert, async collapse, batched rewriter.

Reports from sprint executions land in [`plans/reports/`](../plans/reports/).

## Key Topics by Role

### Backend Development
- Code standards: [code-standards.md](./code-standards.md) — Python conventions, design patterns
- Architecture: [system-architecture.md](./system-architecture.md) — Service organization, API design
- Codebase: [codebase-summary.md](./codebase-summary.md) — Services, database schema, key files

### Frontend Development
- Code standards: [code-standards.md](./code-standards.md#frontend-standards-typescript) — TypeScript style, Alpine.js patterns
- Architecture: [system-architecture.md](./system-architecture.md#frontend-stack) — SPA structure, dark/light mode

### DevOps / Operations
- Deployment: [deployment-production.md](./deployment-production.md) — Docker Compose, Redis, Nginx, monitoring
- Architecture: [system-architecture.md](./system-architecture.md#deployment-architecture) — Single & multi-instance setups
- Health: [deployment-production.md](./deployment-production.md#health-check-endpoints) — Health check endpoints

### Security & Compliance
- Standards: [code-standards.md](./code-standards.md#security-best-practices) — Error handling, secret management
- Architecture: [system-architecture.md](./system-architecture.md#security-architecture) — JWT, CORS, TLS/SSL, audit logging
- Deployment: [deployment-production.md](./deployment-production.md#ssltls) — SSL/TLS certificates, Let's Encrypt

## P3 Sprint Highlights

All documentation has been updated to reflect P3 sprint changes:

### 1. Production Redis Security
- Password authentication enabled via `--requirepass`
- Health checks updated to use `-a` flag
- See: [deployment-production.md](./deployment-production.md#redis-security)

### 2. Horizontal Scaling Support
- Nginx `ip_hash` sticky sessions for SSE stream routing
- Multi-instance deployment via `docker compose --scale app=3`
- See: [deployment-production.md](./deployment-production.md#horizontal-scaling) and [system-architecture.md](./system-architecture.md#2-nginx-sticky-sessions-for-horizontal-scaling)

### 3. Enhanced Health Checks
- New `scale_ready` field indicates readiness for multi-instance deployment
- Cached SQLAlchemy engine for faster repeated probes
- See: [deployment-production.md](./deployment-production.md#health-check-endpoints)

### 4. Deprecation Warnings
- Browser auth deprecated in v3.x, removed in v4.0
- Clear migration path to API key authentication
- See: [deprecations-v4-migration.md](./deprecations-v4-migration.md)

## Common Tasks

### "I need to set up a production deployment"
→ Start with [deployment-production.md](./deployment-production.md)

### "I'm new to the codebase"
→ Read [codebase-summary.md](./codebase-summary.md) then [system-architecture.md](./system-architecture.md)

### "I need to write a new API endpoint"
→ Check [code-standards.md](./code-standards.md#design-patterns) and [codebase-summary.md](./codebase-summary.md#api-endpoints)

### "I need to scale to multiple instances"
→ Review [deployment-production.md](./deployment-production.md#horizontal-scaling)

### "I'm using browser auth and need to migrate"
→ Follow [deprecations-v4-migration.md](./deprecations-v4-migration.md)

### "I need to understand system requirements"
→ See [project-overview-pdr.md](./project-overview-pdr.md)

## Additional Resources

- **GitHub**: https://github.com/HieuNTg/STORYFORGE
- **Issues**: Report bugs or suggest features
- **Discussions**: Ask questions or discuss architecture
- **Contributing**: See [CONTRIBUTING.md](../CONTRIBUTING.md) in the root

## Documentation Maintenance

Documentation is kept up-to-date alongside code changes. When submitting PRs that affect:
- **Deployment**: Update [deployment-production.md](./deployment-production.md)
- **Architecture**: Update [system-architecture.md](./system-architecture.md)
- **Code patterns**: Update [code-standards.md](./code-standards.md)
- **APIs**: Update [codebase-summary.md](./codebase-summary.md#api-endpoints)
- **Deprecations**: Update [deprecations-v4-migration.md](./deprecations-v4-migration.md)

## Quick Answers

**Q: How do I deploy to production?**
A: See [deployment-production.md](./deployment-production.md) — `docker compose --env-file .env.production -f docker-compose.production.yml up -d`

**Q: How do I scale to multiple instances?**
A: See [deployment-production.md](./deployment-production.md#horizontal-scaling) — requires Redis + PostgreSQL + nginx sticky sessions

**Q: Is browser authentication still supported?**
A: Yes in v3.x (with deprecation warning), removed in v4.0. See [deprecations-v4-migration.md](./deprecations-v4-migration.md) for migration.

**Q: What are the health check endpoints?**
A: `/api/health` (fast) and `/api/health/deep` (full subsystem probe). See [deployment-production.md](./deployment-production.md#health-check-endpoints)

**Q: How do I contribute?**
A: See [CONTRIBUTING.md](../CONTRIBUTING.md) and follow [code-standards.md](./code-standards.md)

---

**Last Updated**: 2026-05-04 | **Sprint 1 / 2 / 3 merged to master**
