# StoryForge Frontend

Next.js (App Router) UI for StoryForge. It talks to the FastAPI backend at `http://localhost:7860` via the typed client in [`lib/api/`](lib/api), and exposes the current shell at `http://localhost:3001` during local development.

## Stack

- **Next.js 16** App Router · React 19 · TypeScript strict
- **Tailwind CSS** + shadcn-style primitives in [`components/ui/`](components/ui)
- **TanStack Query** for server state ([`lib/api/queries.ts`](lib/api/queries.ts))
- **React Hook Form** + **Zod** for typed forms / schemas ([`lib/schemas/`](lib/schemas))
- **MSW** for browser + node API mocking in tests
- **Sonner** for toasts; **Lucide** icons

## Dev

```bash
# from repo root, in a second terminal alongside `python app.py`
cd frontend
npm install
npm run dev -- --port 3001   # http://localhost:3001 (proxies API calls to :7860)
npm run lint
npx tsc --noEmit   # typecheck (no script alias yet)
npm test           # vitest + RTL
```

## Layout

```
app/                     # App Router pages (shell routes: forge, library, reader, branching, simulation, settings)
components/
  settings/              # Settings tab forms (General, API keys/provider quick-add, Advanced L1/L2, Flowkit)
  reader/                # Library-backed reader start screen + chapter reader
  branching/             # Library-backed branch starter + branch tree
  simulation/            # Library/story/character-driven simulation setup
  story/                 # Story editor and pipeline surfaces
  ui/                    # shadcn primitives (Button, Input, Switch, Badge, ...)
lib/
  api/                   # Typed fetch client + TanStack Query hooks
  schemas/               # Zod schemas mirroring backend Pydantic models
  utils.ts               # cn() classname helper
```

## Conventions

- Schema source of truth lives in backend Pydantic. Mirror in `lib/schemas/*.ts` with `z.object(...).strict()`; `.default()` keeps fields optional in inputs but populated in parsed outputs.
- Forms use `pickDirty()` to PATCH only changed fields (delta PATCH against `/api/config`, `/api/stories/{id}`, etc.).
- Long-lived components that mirror server state must derive `initial` via `useMemo` and key resets on a stable `JSON.stringify(initial)` so background refetches don't clobber in-flight edits.
- Provider-specific config panels (e.g., [`FlowkitSettings`](components/settings/FlowkitSettings.tsx)) mount conditionally and own their own RHF instance, leaving the General tab's delta-save flow untouched.

## Notes

- This is **not** stock Next.js — read [`AGENTS.md`](AGENTS.md) before relying on training-data assumptions about APIs / conventions.
- Heed deprecation notices in `node_modules/next/dist/docs/`.
- Don't reintroduce the legacy `web/` Alpine SPA — it's been removed.

## Current UX map

- `/forge/` renders the main story creation pipeline.
- `/library/` is the local source of truth for saved stories.
- `/reader/`, `/branching/`, `/simulation/`, and `/characters/` start by choosing a story from the local library. Avoid fake `demo` routes/sessions.
- `/settings/` owns provider setup:
  - **General**: language, image provider, image prompt style select. Legacy raw `model` / `base_url` fields are hidden.
  - **API Keys**: quick-add provider cards for Gemini, Anthropic, OpenAI, OpenRouter Free, Z.AI, Kyma; each card has a model dropdown and API key field.
  - **Advanced L1/L2**: `cheap_model`, `layer1_model`, and `layer2_model` are dropdowns populated from configured provider profiles.
- `/providers/` shows configured provider profiles only; the legacy `Primary` / `Mặc định` row should not be reintroduced.

## Select/value convention

Base UI Select must stay controlled for its whole lifetime. Use sentinel values such as `""` or `"__default__"`; do not pass `undefined` as `value` and later replace it with a real value.
