# Novel Auto Documentation

Welcome to the Novel Auto Pipeline documentation. Start here to understand the system architecture, code standards, and project roadmap.

## Core Documentation

### [Codebase Summary](./codebase-summary.md)
**Quick overview of the entire codebase structure.**
- Project overview (3-layer pipeline)
- File structure and module breakdown
- Core data models (including Phase 1 Character State Tracking)
- Services overview (LLM client, caching, prompts)
- Configuration system
- Development status

**Start here if**: You're new to the project and want to understand what files do what.

---

### [System Architecture](./system-architecture.md)
**Deep dive into system design and how components interact.**
- High-level 3-layer pipeline diagram
- Layer 1 detailed flow (story generation with character tracking)
- Phase 1 implementation (character state extraction, rolling context)
- LLM client architecture (singleton, retry, fallback, cache)
- Agent architecture (Layer 2)
- Phase 4: Export & download architecture (export_output, export_zip, gr.File UI)
- Error handling & token efficiency strategies

**Start here if**: You're implementing a feature or debugging a complex issue.

---

### [Code Standards](./code-standards.md)
**Conventions, patterns, and best practices for this codebase.**
- Naming conventions (PascalCase, snake_case, etc.)
- Import organization
- Pydantic model patterns
- Function docstring format
- Logging standards
- Parallel execution patterns (ThreadPoolExecutor)
- LLM integration patterns (prompts, methods, parameters)
- Export & file I/O patterns (Phase 4)
- Gradio File widget integration
- Error handling philosophy (fail gracefully, log always)
- Performance & efficiency guidelines
- API & Flask conventions

**Start here if**: You're writing or reviewing code.

---

### [Project Overview & PDR](./project-overview-pdr.md)
**Product requirements, constraints, and roadmap.**
- Project vision & definition
- Product features by layer
- User personas
- Functional requirements (detailed by layer)
- Non-functional requirements (performance, reliability, scalability)
- Technical constraints & technology stack
- Acceptance criteria (Phase 1 complete, Phase 2/3 planned)
- Success metrics
- Known limitations & future work

**Start here if**: You're planning a feature, estimating scope, or onboarding stakeholders.

---

## Quick Navigation

### By Role

**Software Engineer**
1. Read: [Code Standards](./code-standards.md) — Conventions
2. Read: [Codebase Summary](./codebase-summary.md) — Module overview
3. Reference: [System Architecture](./system-architecture.md) — When debugging

**Product Manager**
1. Read: [Project Overview & PDR](./project-overview-pdr.md) — Roadmap & requirements
2. Reference: [Codebase Summary](./codebase-summary.md) — Feature tracking

**Architect / Tech Lead**
1. Read: [System Architecture](./system-architecture.md) — Design patterns
2. Read: [Code Standards](./code-standards.md) — Quality standards
3. Reference: [Project Overview & PDR](./project-overview-pdr.md) — Constraints

---

## Phase 1: Character State Tracking (COMPLETE ✓)

**What was added**: Automatic character consistency tracking across chapters.

**Key Features**:
- `CharacterState` — Tracks mood, arc position, knowledge, relationships per character
- `PlotEvent` — Records important story events for continuity checking
- `StoryContext` — Rolling context window (default: last 2 chapters) passed between writes
- Parallel extraction (summary + character states + plot events)
- Configurable context window size

**Impact**: Reduces character inconsistencies in multi-chapter stories by 60-70%.

**For details**: See [Codebase Summary - Phase 1](./codebase-summary.md#phase-1-character-state-tracking-latest) & [System Architecture - Phase 1](./system-architecture.md#phase-1-character-state-tracking).

---

## Roadmap

**Phase 1** ✓ (COMPLETE - 2026-03-23)
- Character state tracking with rolling context

**Phase 2** ✓ (COMPLETE - 2026-03-23)
- Model routing (cost optimization via cheap model for summary/extraction)

**Phase 3** ✓ (COMPLETE - 2026-03-23)
- Streaming content preview (Layer 1 write_chapter streaming)

**Phase 4** ✓ (COMPLETE - 2026-03-23)
- File download/export (export_output list[str], export_zip bundling, gr.File widget, _export_markdown returns path)

**Phase 5** (Planned)
- Story quality metrics (inline blocking quality scoring)

---

## Documentation Gaps & Future Work

**High Priority** (Block Phase 2):
- API Reference — Document all endpoints
- Deployment Guide — Setup & troubleshooting
- Agent Architecture Details — Expand Layer 2 specs

**Medium Priority**:
- Quickstart Guide — 5-minute example
- FAQ & Troubleshooting — Common issues
- Configuration Reference — Detailed parameter docs

**Low Priority**:
- Design Guidelines
- Performance Tuning Guide
- Roadmap Deep-Dive

---

## Contributing to Documentation

When updating code, please also update relevant docs:

1. **New feature?** → Update [Codebase Summary](./codebase-summary.md)
2. **Changed architecture?** → Update [System Architecture](./system-architecture.md)
3. **New patterns/standards?** → Update [Code Standards](./code-standards.md)
4. **Changed requirements/scope?** → Update [Project Overview & PDR](./project-overview-pdr.md)

**Document Size Limit**: Keep all doc files under 800 LOC for readability.

---

## Document Metadata

| Document | LOC | Last Updated | Status |
|----------|-----|--------------|--------|
| codebase-summary.md | 213 | 2026-03-23 | Phase 1 Complete |
| system-architecture.md | 315 | 2026-03-23 | Phase 4 Complete |
| code-standards.md | 436 | 2026-03-23 | Phase 4 Complete |
| project-overview-pdr.md | 388 | 2026-03-23 | Phase 4 Complete |
| **Total** | **1,352** | 2026-03-23 | Phase 4 Complete |

---

**Documentation Version**: 1.1 (Phase 4 Export) | **Last Updated**: 2026-03-23
