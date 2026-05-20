# Frontend Security — API Key Handling (Phase 3)

Scope: audits the planned Settings/Providers/Export pages in `frontend/` (Next.js App
Router) against the StoryForge open-source, self-hosted deployment model. Targets the
spec at `plans/260519-1908-ui-rebuild-react-shadcn/phase-03-settings-providers-export.md`.

This is a **single-user, self-hosted, same-origin** application. Threat model is NOT
multi-tenant SaaS. Host compromise = game over (out of scope).

---

## 1. Deployment & Threat Model

### Deployment shape

- FastAPI serves the static `frontend/out/` bundle on `:7860` (same-origin).
- No auth guards (per `feedback_no_auth.md`). User runs StoryForge on own machine.
- Browser stores: only non-sensitive UI prefs (sidebar, theme, reader settings).
- Secrets live in `config.json` on the host filesystem (managed by `ConfigManager`).

### Actors

| Actor | Capability | In scope |
|---|---|---|
| Legitimate user | Full access to their own keys | Yes (expected) |
| Browser extension | Read DOM, `localStorage`, `console`, network responses (without origin) | Yes — keep keys off these surfaces |
| Screen-share / pair / over-shoulder | Visual reader of monitor | Yes — mask on screen by default |
| Public-repo commit accident | Devs commit browser state or fixtures | Yes — no real-looking placeholders, no state fixtures |
| DevTools observer (support session) | Sees React props, network panel, console | Partial — accepted leak surface (documented) |
| Local malware / host compromise | Reads disk, memory | **Out of scope** (single-user host trust) |
| Network attacker (non-HTTPS) | MITM on plain HTTP | Out of scope (localhost) — but secure cookie flag should still flip on HTTPS |

### Assets

- LLM provider API keys (`llm.api_key`, `llm.api_keys[]`, `llm.fallback_models[*].api_key`, `pipeline.hf_token`).
- Severity if leaked: **High** — attacker burns user's paid quota and/or exfiltrates request history at provider.

---

## 2. Audit Findings

| # | Risk | Vector | Status | Required Mitigation |
|---|---|---|---|---|
| F1 | API key in URL/query state (nuqs, `?key=...`, `history.pushState`, `location.hash`) | URL leak via referrer header, browser history, screen-share | Open (Frontend) | Hard rule: never put `api_key`, `hf_token`, `seedream_api_key`, `replicate_api_key`, `layer1_api_key`, `layer2_api_key`, `image_api_key`, `long_context_api_key` into nuqs schema. Keep entirely in RHF form state. |
| F2 | Zustand `persist` writes key to `localStorage` | Plain-text persistence read by extensions | Mitigated (spec) | Spec already forbids `persist` on api_key. `settings-store.ts` may only persist UI prefs (selectedProvider id, lastTab). Add ESLint rule or grep check (see §4). |
| F3 | Backend echoes plaintext key on `GET /api/config` | Response cached by browser/extensions; React Query cache holds plaintext | **Mitigated (backend)** | Confirmed in `api/config_routes.py:140-156`: returns `api_key_masked` and `api_keys_masked`. Frontend must consume the masked field; never store the user-typed plaintext key in React Query cache. |
| F4 | PUT body echoed back into form on save success | Plaintext key resurfaces in Query cache and devtools after save | Open (Frontend) | On `PUT /api/config` success: (a) clear the password input value, (b) `queryClient.invalidateQueries(['config'])` to force a fresh masked GET, (c) do NOT optimistic-update the cache with the plaintext key. Spec says "optimistic update via Query" — restrict optimism to non-secret fields only. |
| F5 | Sending unchanged masked key back to PUT | Backend overwrites real key with `"sk-***1234"` (mask becomes the key); also leaks masked form via wire | **Mitigated (backend)** + Open (Frontend) | Backend `ConfigUpdate.api_key: Optional[str] = None` — `None` means "no change". **Frontend must use delta-update**: only include `api_key` in PUT body if user typed a new value. Same for `hf_token`. Never send the masked echo back. |
| F6 | `console.log(config)` / debug toast echoes body | Plaintext key lands in console — persists in DevTools, screen-recordings, error monitors | Open (Frontend) | Hard rule: no `console.log`/`console.error` of form values or response bodies in settings code. Toast `description` must be a static string, not `err.message` if `err.cause?.body` could contain key. |
| F7 | Clipboard auto-copy or `navigator.clipboard.writeText` | Key on clipboard until next copy; pasted into chat by accident | Open (Frontend) | No copy-on-focus, no drag handlers, no clipboard writes of the key. If "copy key" feature added later, must be explicit user click + auto-clear after 30s. |
| F8 | Key in `data-*` attr, `title`, `aria-label`, `aria-describedby` | Extension reads DOM attrs cheaply | Open (Frontend) | `MaskedInput` must keep value only in `value` prop (React state). No `data-original-key`, no `title={key}`, no aria announcement of value. Use `aria-label="API key"` (static). |
| F9 | `<input type="text">` instead of `type="password"` | Visible on screen; OS-level screenshot redaction often skips text inputs | Open (Frontend) | `MaskedInput` must default to `type="password"`. Reveal toggle allowed (button changes to `type="text"`), but default state and after-blur state must be `password`. After save, force back to `password`. |
| F10 | React DevTools shows component state plaintext | Anyone with devtools (incl. user during support session) sees key | **Accepted** | DevTools = trusted local user. Document the risk. Mitigation if needed later: `useRef` instead of `useState` for the key, but breaks controlled-input pattern. Not worth the cost for OSS. |
| F11 | Browser autofill / password manager save prompt | OS prompts to save key into keychain | Open (Frontend) | Add `autoComplete="off"` + `name="storyforge-api-key"` (non-standard name) on key inputs. Add `data-1p-ignore` and `data-lpignore="true"` for 1Password / LastPass. Document that users may still choose to save to keychain. |
| F12 | CSRF missing on `PUT /api/config` | CSRF via malicious site (low risk same-origin, but cheap to fix) | **Mitigated** | `lib/api/client.ts:71-72` reads `csrf_token` cookie and injects `X-CSRF-Token`. `middleware/csrf.py` enforces double-submit on non-GET, exempts only `/docs`, `/redoc`, `/openapi.json`, `/api/health`, `/mcp/`. `/api/config` is not exempt — confirmed enforced. |
| F13 | Error response body echoed verbatim to user toast | Backend error may include key fragment if validation regex echoes input | Open (Frontend) | `apiFetch` already wraps errors in `ApiError`. Settings page must show `err.message` only when the message is from `error.code` enum, not raw validator text. Better: map error codes to localized Vietnamese strings, ignore raw `details`. |
| F14 | Wizard dismiss flag uses `localStorage` | Not a leak — just verifying it doesn't store the key | **Mitigated** | Legacy `web/js/pages/settings.ts:447-471` only persists a `forge_wizard_dismissed` boolean. Port must not extend this to persist key/profile data. |
| F15 | Provider table shows masked key in cell text | Visual exposure during screen-share is intended; ensure source value is the masked echo, never the plaintext form value | Open (Frontend) | `ProviderRow` reads `api_key_masked` from `GET /api/config` response only. Never re-renders the plaintext value the user just typed. After save, refetch and re-render from masked echo. |
| F16 | Test fixtures contain real-looking keys | Public-repo commit leaks via `frontend/lib/api/__mocks__/handlers.ts` or playwright fixtures | Open (Frontend) | Fixture keys must be obvious placeholders: `sk-test-FAKE-DO-NOT-USE-0000` or similar. No `sk-proj-` / `sk-ant-` / `AIza` prefixes that could match real-key regex scanners or look real to humans. |
| F17 | Service Worker / Next.js prefetch caches `GET /api/config` response | Masked is fine, but if backend ever regresses to plaintext, SW caches it | Defense in depth | Set `Cache-Control: no-store` on `GET /api/config` server-side OR set `staleTime: 0, gcTime: 0` for the `['config']` query. Recommended: `gcTime: 0` since UI does not need offline config. |
| F18 | SSR/RSC serializes config props | Next.js dehydrates state to HTML — appears in page source | **Mitigated** | Phase 3 spec uses static export (`output: 'export'`) and client components for settings forms. `GET /api/config` is called from a `"use client"` query hook — never during build/RSC. Verify no `loader`/`getServerSideProps` analog adds the config call to a server component. |
| F19 | Sentry/error-reporter integration captures form state on crash | Plaintext key shipped to Sentry / Datadog | Not applicable now | No error reporter is wired in Phase 3. If added later, **must** scrub `api_key`, `api_keys`, `hf_token`, `*_api_key` from `beforeSend` hook. Document in this file when integrated. |

---

## 3. Implementation Requirements for Frontend Developer

The Frontend Developer building Phase 3 must satisfy this checklist in code. Each item maps to a finding above.

### 3.1 Form & state

- [ ] `ApiKeysForm.tsx`: all key fields use shadcn `Input` with `type="password"` by default. Reveal toggle is per-field, resets to `password` on blur and after save.
- [ ] No `value` of any key field appears in `nuqs` schema, URL, or `router.push`.
- [ ] `settings-store.ts` Zustand store may persist ONLY: `selectedProviderTab`, `wizardDismissed`. **Forbidden** to persist: `api_key`, `api_keys`, `hf_token`, `seedream_api_key`, `replicate_api_key`, `*_api_key`, raw `config` object.
- [ ] React Query `['config']`: `staleTime: 0`, `gcTime: 0` (or near-zero). The cache holds masked values only; refetch on every settings page mount.
- [ ] After `PUT /api/config` success: invalidate `['config']`, reset RHF form key inputs to empty string (not to masked echo).
- [ ] Inputs have `autoComplete="off"`, `data-1p-ignore`, `data-lpignore="true"`, `spellCheck={false}`.

### 3.2 Network

- [ ] PUT body is **delta-only**: include `api_key` field only if user typed a fresh value (RHF `dirtyFields` gate). Never send back the masked echo from `GET`.
- [ ] CSRF: rely on `apiFetch` from `lib/api/client.ts` — do NOT bypass with raw `fetch()` for settings mutations.
- [ ] No `body: JSON.stringify(formValues)` blind-dump — explicit object construction per field.

### 3.3 Logging & errors

- [ ] No `console.log`/`console.warn`/`console.error` in settings/providers code paths that include `formValues`, `data`, `config`, `err.cause`, `err.details`, or response bodies.
- [ ] Toast messages use translated strings keyed by `error.code`. Raw `error.message` only shown for HTTP `5xx` and only as "Server error — see logs".
- [ ] Build-time: ensure `NEXT_PUBLIC_*` env vars never contain a key. Document in `.env.example` that LLM keys belong in `config.json` server-side.

### 3.4 DOM exposure

- [ ] Masked input field has no `data-*` attr containing the value.
- [ ] `aria-label` is static ("API key", "Khoá API"); never includes the value.
- [ ] Provider table renders only `api_key_masked` from server response. Never re-renders plaintext typed value after save.
- [ ] Wizard step that shows the typed key does so only on the active page; never in a toast, never in a copy-to-clipboard target.

### 3.5 Fixtures & tests

- [ ] Test fixture keys are obvious placeholders: `sk-test-FAKE-DO-NOT-USE-0000`, `AIza-FAKE-...`, etc. Reject keys matching real provider prefix regex.
- [ ] Playwright tests for `/settings` use `data-testid="api-key-input"` and never assert on plaintext value of the masked echo.
- [ ] `.gitignore` covers `.env.local`, `frontend/.env*`, `frontend/playwright/.auth/` — verify before merge.

---

## 4. Build-Time Grep Checks (PowerShell)

Run before each Phase 3 commit. Place these in `scripts/check-security.ps1` (optional)
or run ad hoc. Each command must produce zero matches.

```powershell
# F2: No Zustand persist of api_key
Get-ChildItem -Path frontend\stores,frontend\components,frontend\app -Recurse -Include *.ts,*.tsx |
  Select-String -Pattern 'persist\s*\([^)]*api_key|persist\s*\([^)]*hf_token'

# F6: No console.log of form values / config in settings code
Get-ChildItem -Path frontend\app\(shell)\settings,frontend\components\settings,frontend\app\(shell)\providers,frontend\components\providers -Recurse -Include *.ts,*.tsx |
  Select-String -Pattern 'console\.(log|warn|error|debug|info)\s*\([^)]*\b(config|api_key|hf_token|form|values|data)\b'

# F1: No nuqs / URL state for api_key
Get-ChildItem -Path frontend -Recurse -Include *.ts,*.tsx -Exclude node_modules |
  Select-String -Pattern 'useQueryState\s*\(\s*["''](api_key|hf_token|.*_api_key)'

# F1b: No router.push or history with key
Get-ChildItem -Path frontend\app\(shell)\settings,frontend\components\settings -Recurse -Include *.ts,*.tsx |
  Select-String -Pattern '(router\.push|router\.replace|history\.(pushState|replaceState))\s*\([^)]*api_key'

# F7: No clipboard writes of key
Get-ChildItem -Path frontend\app\(shell)\settings,frontend\components\settings -Recurse -Include *.ts,*.tsx |
  Select-String -Pattern 'clipboard\.writeText\s*\([^)]*\b(api_key|hf_token|key)\b'

# F8: No key in data-* / title / aria-label value
Get-ChildItem -Path frontend\app\(shell)\settings,frontend\components\settings -Recurse -Include *.ts,*.tsx |
  Select-String -Pattern 'data-[a-z-]+=\{.*api_key|title=\{.*api_key|aria-label=\{.*api_key'

# F16: No real-looking key in fixtures
Get-ChildItem -Path frontend\lib\api\__mocks__,frontend\tests -Recurse -Include *.ts,*.tsx,*.json |
  Select-String -Pattern '(sk-proj-|sk-ant-|sk-or-|AIza[A-Za-z0-9_-]{10,})'

# F9: type="password" present on key fields
Get-ChildItem -Path frontend\components\settings -Recurse -Include *.tsx |
  Select-String -Pattern 'type=["'']password["'']' -NotMatch
# (manual review — confirm every Input rendering api_key has type="password")
```

Exit non-zero on any match → wire into CI later if desired.

---

## 5. Single-User OSS Deployment Notes

- StoryForge is meant to run on the user's own machine. The security boundary is the
  host, not the application.
- The masked-echo pattern on `GET /api/config` is correct and already implemented in
  `api/config_routes.py`. **Do not regress it** — any change that returns plaintext
  to the browser must be rejected at code review.
- CSRF middleware (`middleware/csrf.py`) is enforced for `/api/config` PUT. Keep it.
- If multi-tenant deployment is ever proposed, **this entire document needs revision**.
  Notable gaps for that scenario:
  - No auth on `/api/config` routes (OSS-by-design; RBAC stubs exist in `api/config_routes.py:1-34` but are wired off).
  - `provider_status_routes.py:_get_api_keys_from_config()` reads env vars including
    `ANTHROPIC_API_KEY`, `GOOGLE_AI_API_KEY`, `ZAI_API_KEY` — fine for single-user,
    catastrophic for multi-tenant.
- HTTPS is the host operator's responsibility. The CSRF cookie auto-flips `secure=True`
  when `x-forwarded-proto: https` is observed (see `middleware/csrf.py:45-55`).

---

## 6. Backend Asks (for Phase 5 cutover or earlier)

Confirmed already in place — no changes required for Phase 3:

- `GET /api/config` masks `api_key`, `api_keys`, `hf_token`, and per-profile keys.
- `PUT /api/config` accepts `Optional[str] = None` — supports delta updates.
- CSRF middleware enforces double-submit on `PUT /api/config`.

Nice-to-have (defense-in-depth, not blocking):

- Add `Cache-Control: no-store, private` to `GET /api/config` response headers.
- Reject `PUT /api/config` if `api_key` value matches the masked pattern
  (`^.{4,6}\*\*\*.{4}$`) — protects against frontend bug where it echoes the mask
  back. Currently if the frontend regresses, the mask becomes the stored key.
- Audit-log writes for "api_key changed" / "profile added" — useful even in OSS for
  the user's own forensics. Mask the value in the log line.

---

## 7. Unresolved Questions

1. Will Phase 3 add an error-reporting integration (Sentry, Datadog, console-shipping)?
   If yes, scrub list must be added before launch. Currently no such integration is
   planned per Phase 3 spec — assumption only.
2. Does the Phase 3 wizard ever need to display the plaintext key back to the user
   after save (e.g., "Save and show once")? Spec doesn't require this. Recommend
   never; show masked echo only.
3. Should we add a `MaskedInput` shadcn primitive that enforces `type="password"`,
   `autoComplete="off"`, and the no-`data-*`-leak rule by construction, vs. relying on
   reviewer discipline? Recommend yes — single component, one place to audit.
4. The `data-1p-ignore` / `data-lpignore` attrs deter password managers but don't
   prevent OS keychain offers (Windows credential manager). Acceptable risk?
