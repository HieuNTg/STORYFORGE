# StoryForge Documentation

## Core docs

| Doc | Audience | Purpose |
|-----|----------|---------|
| [system-architecture.md](./system-architecture.md) | Architects, DevOps | Pipeline flow, signal integration, retry semantics |
| [code-standards.md](./code-standards.md) | Contributors | Python/TypeScript style, design patterns, security |
| [deployment-production.md](./deployment-production.md) | Self-hosters | Production setup, scaling, monitoring |
| [flowkit-integration.md](./flowkit-integration.md) | Image gen users | Google Labs Imagen/Veo, extension install, config |

## Architecture Decision Records

| ADR | Topic |
|-----|-------|
| [0001](./adr/0001-l1-handoff-envelope.md) | Typed `L1Handoff` + `NegotiatedChapterContract` collapse `getattr(..., None) or []` blind spots into one validated chokepoint (Sprint 1) |
| [0002](./adr/0002-semantic-verification.md) | Local CPU embeddings (multilingual MiniLM) + spaCy NER replace keyword payoff/structural/outline checks (Sprint 2) |
| [0003](./adr/0003-generation-hardening-drama-ceiling.md) | `drama_ceiling` injected into chapter writer; speaker-anchored voice revert; async D3 contract; batched structural rewriter (Sprint 3) |

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) at repo root.


## UI notes

- The active UI is the Next.js shell in `frontend/` (dev: `npm run dev -- --port 3001`).
- Library-backed flows are intentional: Reader, Branching, Simulation, and Characters should select an existing local story before doing story-specific work.
- Settings no longer exposes legacy raw primary `model` / `base_url` fields in normal UX. Provider setup happens through API Keys provider profiles; advanced cheap/L1/L2 routing chooses from those profiles.
- Avoid restoring fake routes like `/branching/demo/` or legacy provider rows like `Primary` / `Mặc định`.
