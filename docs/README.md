# StoryForge Documentation

## Core docs

| Doc | Audience | Purpose |
|-----|----------|---------|
| [system-architecture.md](./system-architecture.md) | Architects, DevOps | Pipeline flow, signal integration, retry semantics |
| [code-standards.md](./code-standards.md) | Contributors | Python/TypeScript style, design patterns, security |
| [deployment-production.md](./deployment-production.md) | Self-hosters | Production setup, scaling, monitoring |

## Architecture Decision Records

| ADR | Topic |
|-----|-------|
| [0001](./adr/0001-l1-handoff-envelope.md) | Typed `L1Handoff` + `NegotiatedChapterContract` collapse `getattr(..., None) or []` blind spots into one validated chokepoint (Sprint 1) |
| [0002](./adr/0002-semantic-verification.md) | Local CPU embeddings (multilingual MiniLM) + spaCy NER replace keyword payoff/structural/outline checks (Sprint 2) |
| [0003](./adr/0003-generation-hardening-drama-ceiling.md) | `drama_ceiling` injected into chapter writer; speaker-anchored voice revert; async D3 contract; batched structural rewriter (Sprint 3) |

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) at repo root.
