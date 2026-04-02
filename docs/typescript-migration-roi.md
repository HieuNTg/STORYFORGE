# TypeScript Migration ROI Report

## Current JavaScript Stats

| File | LOC | Complexity |
|---|---|---|
| `web/js/api-client.js` | 146 | High (network layer, error types) |
| `web/js/app.js` | 342 | High (Alpine store, state machine) |
| `web/js/audio-player.js` | 149 | Medium |
| `web/js/branch-reader.js` | 120 | Medium |
| `web/js/error-boundary.js` | 336 | High (error handling hierarchy) |
| `web/js/feedback-widget.js` | 120 | Low |
| `web/js/report-issue.js` | 82 | Low |
| `web/js/storage-manager.js` | 184 | Medium |
| `web/js/pages/account.js` | ~120 | Low |
| `web/js/pages/analytics.js` | ~150 | Medium |
| `web/js/pages/branching.js` | ~180 | Medium |
| `web/js/pages/export.js` | ~130 | Low |
| `web/js/pages/library.js` | ~140 | Medium |
| `web/js/pages/reader.js` | ~160 | Medium |
| **Total** | **~2,359 LOC** | |

## Migration Effort Estimate

| File | Effort (days) | Risk | Priority |
|---|---|---|---|
| `api-client.js` | 0.5 | Low | **High** — shared by all pages |
| `storage-manager.js` | 0.5 | Low | High |
| `audio-player.js` | 0.5 | Low | Medium |
| `branch-reader.js` | 0.5 | Low | Medium |
| `feedback-widget.js` | 0.25 | Low | Low |
| `report-issue.js` | 0.25 | Low | Low |
| `error-boundary.js` | 1.0 | Medium | Medium |
| `app.js` | 2.0 | High (Alpine x-data types) | Low (last) |
| All pages/*.js | 3.0 | Medium | Low |
| **Total** | **~8.5 days** | | |

## Benefits vs Costs

| Factor | Benefit | Cost |
|---|---|---|
| Type safety | Catch API contract violations at compile time | Setup: tsconfig, vite plugin |
| IDE autocomplete | Faster development, fewer typos | ~1 day initial config |
| Refactoring safety | Safe rename/restructure | Developer learning if unfamiliar |
| API client types | Generated from FastAPI OpenAPI schema | Requires openapi-typescript |
| Bundle size | No runtime overhead (types stripped) | None |
| Alpine.js types | Community `@types/alpinejs` available | Minor Alpine magic-prop gaps |

## Recommendation

**Phased migration starting with `api-client.js`.**

Rationale:
1. `api-client.js` is the most impactful file — all pages depend on it
2. Defining request/response types here catches the most bugs
3. Low risk, isolated module, easy to test
4. Can use `// @ts-check` + JSDoc as zero-build step 1 before full TS setup

### Phase 1 (Week 1): `api-client.js` + `storage-manager.js`
- Add `tsconfig.json` with `allowJs: true`, `checkJs: true`
- Annotate with JSDoc types (no compilation needed yet)

### Phase 2 (Week 2-3): Rename to `.ts`, add Vite TS pipeline
- `audio-player.ts`, `branch-reader.ts`, page files

### Phase 3 (Month 2): `app.ts` + Alpine store types
- Most complex — requires Alpine.js `MagicProperties` extension
