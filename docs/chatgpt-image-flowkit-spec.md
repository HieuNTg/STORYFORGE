# ChatGPT Image Generation via FlowKit (Free Plus Web Path) — Implementation Spec

**Status:** Research + spec. Decision is locked (CEO): integrate ChatGPT image gen via the
FREE logged-in `chatgpt.com` web session, FlowKit-style, NOT the paid OpenAI Images API.
**Author:** AI Engineer agent. **Date:** 2026-06-09.
**Scope:** What the anti-bot reality forces, the concrete protocol, the extension + backend
changes, a risk-first build plan, and a documented paid fallback.

> Protocol claims below are time-sensitive and were gathered from live reverse-engineering
> sources (cited inline). ChatGPT web internals change often; treat every header/endpoint
> as "verify against a live HAR before coding," not gospel.

---

## 0. TL;DR feasibility

**A pure FlowKit-style HTTP-replay of the standard `chatgpt.com` web image path is NOT viable
as-is.** The `POST /backend-api/conversation` turn is gated by an **OpenAI Sentinel**
proof-of-work (`openai-sentinel-proof-token`) plus a **Cloudflare Turnstile** token, and the
PoW + Turnstile are produced by **obfuscated/VM bytecode in the page bundle that is NOT exposed
as a callable page-world function** the way `grecaptcha.enterprise.execute()` is for Flow. There
is no clean `window.*` bridge to mint the token; the working reverse-engineering implementations
either (a) re-implement the PoW natively in their own code, or (b) drive the rendered page.

That kills the clean "backend authors `{url,method,headers,body}`, extension replays it"
model that FlowKit uses for Flow, **for the conversation endpoint**.

There are **three** candidate architectures, ranked by our confidence they survive contact:

1. **Page-world `fetch` proxy (RECOMMENDED, "FlowKit-Plus").** The extension does NOT author the
   Sentinel/Turnstile/PoW tokens. Instead the backend authors only the *logical* request (prompt,
   model slug, aspect), hands it to a **content script running in the chatgpt.com page world**, and
   that content script calls the page's own `fetch()` so the page bundle's existing request
   interceptor attaches `openai-sentinel-*` headers itself. We never reimplement the PoW; we let
   the page do it. This is the smallest deviation from FlowKit's spirit, but it requires a real
   page-world driver, not a pure background-fetch replay. **Highest survivability.**
2. **Native PoW re-implementation (HTTP replay, "true FlowKit").** Backend mints the proof token
   itself (FNV-1a / SHA3-512 loop over a browser-config array) and the extension replays the
   conversation POST with `credentials:"include"`. **Brittle** — the config array and hash details
   change with each web build and break silently; Turnstile still has to come from somewhere.
3. **Codex `responses` endpoint (HTTP replay, NO Sentinel).** A separate internal endpoint,
   `POST /backend-api/codex/responses`, accepts `{"model": "...", "tools":[{"type":"image_generation"}]}`
   and streams a **base64 PNG inline** with **no Sentinel/PoW** observed. BUT it authenticates with
   **Codex OAuth tokens from `auth.openai.com/oauth/token`**, not the `__Secure-next-auth.session-token`
   web cookie — i.e. it needs a ChatGPT/Codex OAuth login, refreshable via a refresh token. If we can
   capture/relay that OAuth `access_token`, this is by far the cleanest replay path (no PoW, no
   Turnstile, image bytes inline). **Treat as the spike that could make this trivial.**

**Verdict:** Build **Phase 0 as a feasibility spike on path #3 (Codex responses)** and a parallel
spike on path #1 (page-world fetch). Whichever survives, ship it. Do NOT invest in path #2
(native PoW) unless both spikes fail — it is the highest-maintenance option.

---

## 1. Auth / session model of `chatgpt.com`

The web app is a "backend-for-frontend": the SPA calls `https://chatgpt.com/backend-api/*` and
`https://chatgpt.com/api/auth/*`.
([HAR study](https://alinr.com/experiments/chatgpt-har-architecture-conversation-data.html))

| Credential | Where it lives | Capturable by `webRequest` header-sniff? | Notes |
|---|---|---|---|
| `accessToken` (JWT) | Returned by `GET https://chatgpt.com/api/auth/session` as JSON `{ accessToken: "ey..." }`; the SPA then sends it as `Authorization: Bearer ey...` on every `backend-api` call. | **Yes** — identical to FlowKit's existing Google flow. Sniff `Authorization: Bearer` off `chatgpt.com/backend-api/*` via `onBeforeSendHeaders`. | Short-lived (minutes–~1h). SPA silently re-fetches `/api/auth/session` to refresh. ([ChatGPTReversed](https://github.com/gin337/ChatGPTReversed), [realasfngl/ChatGPT](https://github.com/realasfngl/ChatGPT)) |
| `__Secure-next-auth.session-token` | Cookie (httpOnly). | **No** — httpOnly, not in request headers we can read; rides along only with `credentials:"include"`. | This is the durable login. `/api/auth/session` mints the short-lived JWT from it. |
| `__cf_bm`, `cf_clearance` | Cloudflare cookies. | **No** (httpOnly-ish, managed by CF). Ride along only with `credentials:"include"`. | Required for Cloudflare to not 403 the request. |
| CSRF token | `GET https://chatgpt.com/api/auth/csrf`. | Fetched on demand. | Needed by some `/api/auth/*` calls, not by `backend-api/conversation`. ([ChatGPTReversed](https://github.com/gin337/ChatGPTReversed)) |
| `oai-device-id` | Persistent UUID the SPA sends as a header. | **Yes** (it's a normal request header). | Must be stable across the session. ([realasfngl token pipeline](https://deepwiki.com/realasfngl/ChatGPT/4.2-token-generation-pipeline)) |

**Key consequence for FlowKit:** the Bearer JWT is sniffable exactly like Flow's token, BUT the
Cloudflare + session cookies are httpOnly and CANNOT be sniffed. So unlike Flow (which uses
`credentials:"omit"` + a declarativeNetRequest Referer rewrite), the ChatGPT replay **must use
`credentials:"include"`** so `__cf_bm`/`cf_clearance`/`__Secure-next-auth.session-token` ride
along automatically — which in turn means the fetch must originate from a context with
`chatgpt.com` cookies (the background SW with host permission, or the page itself).

**Codex/OAuth variant (path #3):** uses an OAuth `access_token` (+ `account_id`) refreshed via
`POST https://auth.openai.com/oauth/token` with a stored `refresh_token`; sent as
`Authorization: Bearer` to `backend-api/codex/responses`. This is a *different* token than the
web JWT. ([chatgpt-imagegen](https://github.com/leeguooooo/chatgpt-imagegen))

---

## 2. The image-generation request

### 2a. Standard web path — `POST https://chatgpt.com/backend-api/conversation`

Single endpoint, **SSE response** (`Accept: text/event-stream`, stream terminates with `data: [DONE]`).
There is no separate "make an image" REST endpoint on the web path; image gen is a **tool
invocation inside a normal conversation turn** — you send a user message ("generate an image of
…") and the assistant calls the built-in image tool (4o-native image gen / GPT Image; DALL·E is
being retired May 2026). ([everything-chatgpt](https://github.com/terminalcommandnewsletter/everything-chatgpt),
[OpenAI 4o image gen](https://openai.com/index/introducing-4o-image-generation/))

Minimal turn body (fields confirmed across sources; **slug/model values drift — verify live**):

```jsonc
{
  "action": "next",
  "messages": [{
    "id": "<uuid>",
    "author": { "role": "user" },
    "content": { "content_type": "text", "parts": ["Generate an image: <prompt>"] }
  }],
  "parent_message_id": "<uuid|client_root>",
  "conversation_id": null,                 // null => new conversation
  "model": "auto",                          // web build value drifts (gpt-4o / "auto" / gpt-5.x)
  "history_and_training_disabled": false
}
```

Required request headers (the make-or-break set, see §3):
`Authorization: Bearer <jwt>`, `Accept: text/event-stream`, `oai-device-id`, `oai-language`,
`openai-sentinel-chat-requirements-token`, `openai-sentinel-proof-token`, and (when present)
`openai-sentinel-turnstile-token`.
([ChatGPTReversed](https://github.com/gin337/ChatGPTReversed),
[token pipeline](https://deepwiki.com/realasfngl/ChatGPT/4.2-token-generation-pipeline))

### 2b. Codex path — `POST https://chatgpt.com/backend-api/codex/responses` (NO Sentinel)

```jsonc
POST /backend-api/codex/responses
Headers: Authorization: Bearer <oauth_access_token>, version, originator, session_id
Body: {
  "model": "<gpt-5.x>",
  "tools": [{ "type": "image_generation" }],
  "input": [ { "role": "user", "content": [{ "type": "input_text", "text": "<prompt>" }] } ]
}
```

SSE stream emits: `image_generation_call.in_progress` → `.generating` → `.partial_image` →
`output_item.done` (carries **base64 PNG** in `item.result`) → `response.completed`.
**No second download hop, no file id, no Sentinel/PoW observed.** ([chatgpt-imagegen](https://github.com/leeguooooo/chatgpt-imagegen))

This is the same shape as OpenAI's Responses-API image tool: the SSE
`response.output_item.done` event carries an `item.type === "image_generation_call"` payload.
([4o image gen SSE behaviour](https://www.superhuman.ai/a-complete-guide-to-chatgpt-image-generation-in-2025))

---

## 3. Anti-bot gates (the feasibility crux)

For `POST /backend-api/conversation` the SPA first calls:

`POST https://chatgpt.com/backend-api/sentinel/chat-requirements`
→ response:
```jsonc
{
  "persona": "chatgpt-freeaccount",
  "token": "<requirements_token>",      // → openai-sentinel-chat-requirements-token
  "arkose": { "required": false, ... }, // Arkose largely dormant for chat, can flip on
  "turnstile": { "required": true, "dx": "<bytecode>" },  // Cloudflare Turnstile challenge
  "proofofwork": { "required": true, "seed": "0.81186133b2821174", "difficulty": "073682" }
}
```
([ChatGPTReversed requirements response](https://github.com/gin337/ChatGPTReversed))

Then the SPA must produce, for the conversation POST:

- **`openai-sentinel-chat-requirements-token`** — the `token` echoed back. Trivial.
- **`openai-sentinel-proof-token`** — **proof-of-work**. Hash a base64-encoded ~18-element
  browser-config array (screen res, UA, timezone string, `navigator`/`document`/`window` keys,
  perf counters, core count, a constant `4294705152`, etc.) with **SHA3-512** (some builds:
  FNV-1a), iterating an index `i` up to ~500,000 until `hash[:difficulty_len] <= difficulty`.
  Answer is prefixed `gAAAAA…` and base64-encoded. 1–5 s of CPU per request.
  ([openai-sentinel PoW](https://github.com/leetanshaj/openai-sentinel),
  [token pipeline](https://deepwiki.com/realasfngl/ChatGPT/4.2-token-generation-pipeline))
- **`openai-sentinel-turnstile-token`** — Cloudflare **Turnstile**, generated by executing the
  `turnstile.dx` **bytecode in a VM** (decompiled obfuscated challenge). No clean page-world API.
  ([token pipeline](https://deepwiki.com/realasfngl/ChatGPT/4.2-token-generation-pipeline))

**Can these be minted in-page like FlowKit's grecaptcha bridge? NO clean equivalent.**
- For Flow, `injected.js` calls `grecaptcha.enterprise.execute(siteKey, {action})` — a documented,
  stable, globally-exposed page function. **ChatGPT exposes no analogous `window.__getSentinelToken()`.**
  The PoW + Turnstile logic lives inside the minified bundle's closure and a WASM/VM, not on a
  global. ([token pipeline](https://deepwiki.com/realasfngl/ChatGPT/4.2-token-generation-pipeline))
- The realistic in-page move is therefore NOT "call a bridge function" but **"let the page's own
  `fetch` make the request,"** so its internal interceptor attaches all three headers — i.e. path #1.
- The realistic out-of-page move is **re-implementing PoW natively** (path #2) and still needing a
  Turnstile solver — high maintenance, breaks on every build bump.

**The Codex `responses` endpoint (§2b) is the escape hatch: no Sentinel observed at all.** This is
why Phase 0 prioritizes it.

---

## 4. Getting the image bytes out

**Web/conversation path:** the generated image arrives in the SSE stream as a message part with
`content_type: "image_asset_pointer"` whose `asset_pointer` is `file-service://file-...` (or
`sediment://...`). To get bytes:
1. `GET https://chatgpt.com/backend-api/files/download/{file_id}` (Bearer auth) → JSON
   `{ "download_url": "https://...oaiusercontent.com/...", "status": "success" }` — a **signed,
   short-lived URL (≈5 min)**.
2. `GET` that signed URL → raw PNG/JPEG bytes.

File ids also surface in `message.metadata.attachments[].id` and via
`GET /backend-api/conversation/{id}` (`mapping` node graph). Some builds expose
`GET /backend-api/estuary/content?id=file-...` returning the binary directly.
([conversation exporter](https://gist.github.com/ocombe/1d7604bd29a91ceb716304ef8b5aa4b5),
[HAR study](https://alinr.com/experiments/chatgpt-har-architecture-conversation-data.html))

**Download-host allowlist additions** (backend `_DOWNLOAD_HOSTS` in `flow_service.py:41-47`):
`files.oaiusercontent.com`, `*.oaiusercontent.com` (gate by suffix), `images.openai.com`
(thumbnail/proxy), and `chatgpt.com` (for `estuary/content`). Bytes are served from
`oaiusercontent.com` (signed) — that is the host the downloader must be allowed to hit.

**Codex path:** no download hop — base64 PNG is inline in `output_item.done` `item.result`. Decode
and write. (Simplest of all.)

---

## 5. Rate limits & ban risk (free Plus web path)

- **ChatGPT Plus:** ~50 image prompts per rolling 3-hour window ⇒ ~180–200 images/day at perfect
  cadence, but image prompts also draw down the shared ~160-message budget, so realistic sustained
  throughput is materially lower and throttles harder at peak.
- **Free account:** ~2–3 images/day (24-hour rolling reset). Effectively unusable for a pipeline.
- **Ban/flag risk:** automated traffic on a personal account risks rate-limiting and suspension —
  the same warning FlowService already logs for Google (`log_account_warning`, `flow_service.py:172`).
  Use a **dedicated secondary Plus account**, randomized pacing, and respect 429 backoff.
([AVB 2026 guide](https://aivideobootcamp.com/blog/chatgpt-plus-image-generation-complete-guide-2026/),
[glbgpt limits](https://www.glbgpt.com/hub/how-many-images-can-i-generate-with-chatgpt-5-1-5-0-plus-2025-full-guide/),
[free plan limits](https://www.aifreeapi.com/en/posts/chatgpt-image-generation-limit-free-plan))

> **Product reality check:** StoryForge comic generation fans out *many* panels per page. At
> ~50 prompts / 3h, a single multi-page comic can exhaust a Plus account's image budget in one run.
> Plan for multi-account rotation or accept that ChatGPT is a *premium/secondary* provider, with
> Flow (Imagen) remaining the bulk workhorse. This is a capacity constraint to surface to the CEO.

---

# IMPLEMENTATION SPEC

## A. Feasibility verdict

- **Pure background-fetch HTTP replay of `/backend-api/conversation` (true FlowKit) is NOT viable**
  without us re-implementing the Sentinel PoW (SHA3-512/FNV-1a, ~18-field browser-config, ≤500k
  iters) **and** a Cloudflare Turnstile solver. No `window.*` bridge exists to mint these in-page
  the way `grecaptcha.enterprise.execute()` does for Flow. That work is high-maintenance and breaks
  on every web-build bump.
- **The anti-bot reality forces one of:**
  - **Path #1 (page-world `fetch` driver):** a content script on `chatgpt.com` that issues the
    request via the *page's own* `fetch`, letting the bundle attach Sentinel/Turnstile/PoW headers.
    We then read the SSE in-page (or hand the response back over the bridge). This is **not** the
    "backend authors raw HTTP, extension dumbly replays" model — it is a thin in-page driver.
  - **Path #3 (Codex `responses`):** if we can capture the Codex/ChatGPT OAuth `access_token`, this
    endpoint has **no Sentinel**, streams **base64 PNG inline**, and is a near-trivial HTTP replay.
- **Decision:** spike #3 and #1 first (§D Phase 0). Adopt whichever survives. Path #2 (native PoW)
  is the fallback-of-last-resort, not the plan.

The shared truth for every path: the **SSE-streaming response cannot go through the current
`handleApiRequest`**, which does `res.text()` + `JSON.parse` (`background.js:152-154`) and would
choke on `text/event-stream`. SSE assembly is mandatory new work regardless of path.

## B. Extension changes (`flowkit_extension/`)

1. **`manifest.json` — host permissions & content scripts.**
   - Add `https://chatgpt.com/*` (and `https://auth.openai.com/*` for the Codex token refresh) to
     `host_permissions`.
   - Add `https://*.oaiusercontent.com/*` only if the *extension* (not backend) downloads bytes;
     prefer backend download, so this may be unnecessary.
   - Add a `content_scripts` entry matching `https://chatgpt.com/*` for the page-world driver
     (path #1) — analogous to the existing Flow content script that hosts the captcha bridge.

2. **Token + cookie capture for chatgpt.com.**
   - Extend the `onBeforeSendHeaders` listener filter at **`background.js:242`**
     (`urls: [...aisandbox..., labs.google...]`) to also include `https://chatgpt.com/backend-api/*`,
     and sniff `Authorization: Bearer` there (the JWT).
   - **Replace the single `state.flowKey`** (`background.js:26`) with a **multi-provider token
     registry**, e.g. `state.tokens = { google: <jwt>, chatgpt: <jwt> }`, keyed by which host the
     header came from. `token_captured` WS frames gain a `provider` field; backend stores per
     provider. (Today `flow_key` is a single string in both `background.js` and
     `flow_service.py:119`; this is the central coupling point to break.)
   - The httpOnly cookies (`cf_clearance`, `__Secure-next-auth.session-token`, `__cf_bm`) are
     **NOT** sniffable — do not try. They ride along via `credentials:"include"` (path #2) or are
     simply present in the page context (path #1).

3. **Credentials policy.**
   - Flow uses `credentials:"omit"` + a DNR Referer/Origin rewrite. **ChatGPT must use
     `credentials:"include"`** so Cloudflare + session cookies attach. Do NOT add a DNR Referer
     rewrite for chatgpt.com (Origin/Referer must stay `chatgpt.com`).
   - **Per-provider branch** in `isAllowedFetchUrl` / `handleApiRequest`: choose `omit` vs `include`
     and which token to attach based on the target host. Generalize `ALLOWED_FETCH_HOSTS`
     (**`background.js:11-15`**) into a per-provider allowlist map:
     `chatgpt.com`, `auth.openai.com`, and (if extension-side download) `*.oaiusercontent.com`.

4. **SSE-stream handling in `handleApiRequest` (mandatory rewrite).**
   - Current code (`background.js:146-154`) `await res.text()` then `JSON.parse` — cannot consume a
     `text/event-stream`. Add a streaming branch: when `params.stream === true` (backend sets it),
     read `res.body.getReader()`, decode chunks, split on `\n\n`, parse each `data:` line, and
     **assemble** the terminal result. Two viable shapes:
     - **Buffer-and-return:** accumulate until `[DONE]`/`response.completed`, extract the
       `image_asset_pointer` file id (web path) or the base64 PNG (Codex path), and send ONE WS
       reply `{ id, status, data }` — preserves the existing request/response/`Future` correlation
       in `flow_service._send` unchanged. **Preferred** (least backend churn).
     - **Stream-relay:** forward incremental `{ id, chunk }` frames over WS for progress UI. More
       work; defer.

5. **Page-world bridge for path #1 (if chosen).** New `injected.js`-style MAIN-world script on
   `chatgpt.com` exposing a message-passing entrypoint that calls the page's `fetch` for
   `/backend-api/conversation` (or invokes the in-page send so Sentinel headers attach), reads the
   SSE, and posts the assembled result back to the content script → background → WS. This mirrors
   the existing grecaptcha bridge pattern (`requestCaptchaToken` / `GET_CAPTCHA` /
   `CAPTCHA_RESULT`, `background.js:177-205, 252-257`) but for a full request, not just a token.
   **No Sentinel reimplementation in our code** — that's the whole point.

6. **401/403 re-auth tab spawn.** Generalize the Flow-tab spawn (`background.js:156-162`,
   `https://labs.google/fx/tools/flow`) so a chatgpt.com 401/403 opens `https://chatgpt.com/`
   instead, to refresh the JWT/cookies.

## C. Backend changes

1. **New `ChatGPTService` sibling to `FlowService`** (`services/media/chatgpt_service.py`), same
   singleton + WS + `pending_requests` Future pattern. Reuse `_send` semantics. It authors:
   - **Path #3 (Codex):** one `api_request` with `{ url: ".../backend-api/codex/responses",
     method:"POST", body:{model, tools:[{type:"image_generation"}], input:[...]}, stream:true,
     provider:"chatgpt_codex" }`. Response data = base64 PNG → decode → write file. **No second hop.**
   - **Path #1/#2 (conversation):** `{ url: ".../backend-api/conversation", body:<§2a>, stream:true,
     provider:"chatgpt" }`. On result, read the `file-service://file-...` id, then a SECOND
     `api_request` `GET .../backend-api/files/download/{id}` → `download_url`, then
     `download_to_local(download_url, dest)`.
   - Reuse/clone the recursive `_extract_*` walk (`flow_service.py:625`) to find the asset pointer /
     download_url in the assembled SSE result.

2. **SSE assembly.** Prefer assembly in the extension (B.4 buffer-and-return) so the backend keeps
   its simple one-Future-per-request model. If the backend must assemble, the WS reply becomes a
   sequence of `{id, chunk}` frames and `_send` needs a streaming variant — avoid for v1.

3. **Download-host allowlist.** Extend `_DOWNLOAD_HOSTS` (`flow_service.py:41-47`) with
   `files.oaiusercontent.com` and a suffix check for `*.oaiusercontent.com` (and `images.openai.com`
   if used). Keep it a strict allowlist — same anti-SSRF rationale as the Google hosts.

4. **Provider dispatch seam** in `services/media/image_generator.py`. The `generate()` /
   `generate_with_reference()` if-ladders (lines ~70-85 / ~103-113) branch on `self.provider`
   strings (`"flowkit"`, `"seedream"`, …). Add a `"chatgpt"` (and/or `"chatgpt_codex"`) branch that
   bridges to `ChatGPTService` via the SAME sync→async helper already used for FlowKit
   (`_main_loop` capture + `run_coroutine_threadsafe`, image_generator.py ~324-378). Add config keys
   mirroring `flowkit_*` (`chatgpt_enabled`, `chatgpt_model_slug`, `chatgpt_use_codex_path`,
   `chatgpt_account_warning_shown`) in `config/defaults.py`.

5. **WS endpoint reuse.** `api/flowkit.py` can stay the single WS; add `provider` awareness to
   `token_captured` dispatch (`flowkit.py:57-62`) so a chatgpt JWT updates `ChatGPTService.flow_key`
   not `FlowService.flow_key`. Alternatively a second WS path `/api/ws/flowkit/chatgpt` — but one WS
   with a provider tag is less code.

## D. Phased build plan (riskiest unknown FIRST)

- **Phase 0 — Anti-bot feasibility spike (fail-fast). DO THIS BEFORE ANY PRODUCTION CODE.**
  - **0a (Codex path):** In a logged-in Chrome with the ChatGPT/Codex OAuth token, manually
    `fetch('/backend-api/codex/responses', {credentials:'include', body:{...image_generation...}})`
    from the page console. If it streams a base64 PNG with **no Sentinel 403**, path #3 wins — ship
    it; the rest of this spec mostly collapses to "relay one POST, decode base64."
  - **0b (Page-world fetch):** From the chatgpt.com page console, drive a real image turn via the
    page's own send path and confirm the Sentinel/Turnstile headers attach automatically and the SSE
    yields a `file-service` pointer. If yes, path #1 is viable.
  - **0c (only if 0a+0b fail):** Attempt native PoW. Capture a live
    `sentinel/chat-requirements` response, reproduce the hash loop, and see if a hand-built
    conversation POST returns 200 (not 403/`unsupported_country`/PoW-fail). If this also fails →
    invoke the §E fallback and stop.
  - **Exit criterion:** one of 0a/0b/0c returns a real generated image. Record which, and the exact
    live request shape, in this doc before Phase 1.

- **Phase 1 — Extension plumbing for the winning path.** Manifest host_permissions + chatgpt.com
  token sniff (B.2), multi-provider token registry (replace `state.flowKey`), `credentials:"include"`
  branch, SSE buffer-and-return in `handleApiRequest` (B.4). Unit-test SSE parsing with a recorded
  fixture (no live network — house rule).

- **Phase 2 — Backend `ChatGPTService` + dispatch.** New service, the files/download second hop
  (web path) or base64 decode (Codex path), `_DOWNLOAD_HOSTS` additions, `image_generator.py`
  `"chatgpt"` branch + config keys. Tests with mocked WS results (mirror `tests/test_flowkit.py`).

- **Phase 3 — Hardening.** 401/403 re-auth tab spawn, 429 backoff + account-warning log, pacing/
  jitter, multi-account note, observability parity with FlowKit status endpoint.

## E. Open risks & fallback

**Top risks (ranked):**
1. **Sentinel PoW + Turnstile gate (make-or-break).** If both Phase-0 spikes (#3 Codex and #1
   page-world) fail and only native PoW remains, maintenance cost is high and breakage is silent on
   every web-build bump. *Mitigation:* prefer page-world fetch so the page owns token minting; treat
   native PoW as do-not-build.
2. **Token model mismatch (Codex OAuth vs web JWT).** Path #3's clean endpoint needs an
   `auth.openai.com` OAuth token + refresh token, which is a *different* login than the sniffable web
   JWT and may not be capturable from a vanilla chatgpt.com session. *Mitigation:* validate token
   capture in 0a before committing to path #3.
3. **Capacity / ban.** ~50 img/3h (Plus) can't feed multi-panel comic fan-out; personal-account
   automation risks suspension. *Mitigation:* dedicated secondary account(s), pacing/jitter, keep
   Flow as the bulk workhorse and position ChatGPT as a premium/selective provider. Surface the
   capacity ceiling to the CEO.
4. **Protocol drift.** Model slugs, the config array, endpoint paths, and even the Codex endpoint's
   existence change without notice. *Mitigation:* pin nothing from memory; keep a "re-capture HAR"
   runbook; fail loudly with the full response logged (as FlowService already does).

**Documented fallback — paid `gpt-image-1` / GPT Image API.** If the free web path proves too
brittle, add a first-class **paid OpenAI Images provider** (`provider="gpt_image"`): a backend-only
`POST https://api.openai.com/v1/images/generations` (or the Responses API image tool) with an
`OPENAI_API_KEY`, no extension, no Sentinel, stable contract, signed/inline bytes. This is the same
`generate()` if-ladder seam (§C.4) and is the reliability floor. It costs money (the CEO explicitly
deprioritized it) but is the guaranteed-working escape hatch and should be stubbed behind a config
flag so it can be switched on instantly if the free path degrades.
([OpenAI Images API guide](https://platform.openai.com/docs/guides/image-generation))

---

## Sources

- HAR architecture study — backend-api BFF, conversation mapping, file content, sentinel prepare/finalize: https://alinr.com/experiments/chatgpt-har-architecture-conversation-data.html
- ChatGPTReversed — requirements response shape, conversation headers, auth/session JWT, csrf: https://github.com/gin337/ChatGPTReversed
- realasfngl/ChatGPT token pipeline — sentinel order, PoW (FNV-1a/native), Turnstile bytecode, header names: https://deepwiki.com/realasfngl/ChatGPT/4.2-token-generation-pipeline and https://github.com/realasfngl/ChatGPT
- openai-sentinel — PoW algorithm (SHA3-512, config array, seed/difficulty, gAAAAA prefix), sentinel/req flow: https://github.com/leetanshaj/openai-sentinel
- everything-chatgpt — conversation request body fields (action/messages/model/parent_message_id), SSE `[DONE]`: https://github.com/terminalcommandnewsletter/everything-chatgpt
- chatgpt-imagegen — Codex `backend-api/codex/responses` endpoint, image_generation tool, base64 PNG SSE, OAuth refresh, NO sentinel: https://github.com/leeguooooo/chatgpt-imagegen
- Conversation exporter — `backend-api/files/download/{id}` → signed download_url, `image_asset_pointer` / `file-service://`: https://gist.github.com/ocombe/1d7604bd29a91ceb716304ef8b5aa4b5
- OpenAI 4o image generation — native tool replacing DALL·E, SSE `image_generation_call` item: https://openai.com/index/introducing-4o-image-generation/ and https://www.superhuman.ai/a-complete-guide-to-chatgpt-image-generation-in-2025
- Rate limits — Plus ~50 img/3h, free ~2–3/day: https://aivideobootcamp.com/blog/chatgpt-plus-image-generation-complete-guide-2026/ , https://www.glbgpt.com/hub/how-many-images-can-i-generate-with-chatgpt-5-1-5-0-plus-2025-full-guide/ , https://www.aifreeapi.com/en/posts/chatgpt-image-generation-limit-free-plan
- Paid fallback — OpenAI Images API: https://platform.openai.com/docs/guides/image-generation
