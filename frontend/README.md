# StoryForge Frontend

Next.js (App Router) UI for StoryForge — replaced the legacy Alpine SPA at `web/` (now removed). Talks to the FastAPI backend at `http://localhost:7860` via the typed client in [`lib/api/`](lib/api).

## Stack

- **Next.js 15** App Router · React 19 · TypeScript strict
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
npm run dev        # http://localhost:3000 (proxies API calls to :7860)
npm run lint
npx tsc --noEmit   # typecheck (no script alias yet)
npm test           # vitest + RTL
```

## Layout

```
app/                     # App Router pages (route groups for stories, settings, branches)
components/
  settings/              # Settings tab forms (General, API keys, Advanced, Flowkit)
  story/                 # Story editor, branch tree, chapter reader
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
