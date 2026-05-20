---
title: FlowKit Integration — Google Labs Proxy (Imagen 3 + Veo)
date: 2026-05-21
status: shipped
tags: [flowkit, image-generation, video-generation, chrome-extension]
---

## Context

Shipped the FlowKit integration: a local-only image/video provider that proxies Imagen 3 + Veo through an authenticated Google Labs browser session via a MV3 Chrome Extension. Delivered in 17h across 6 phases on `master`. Strictly gated for local development — not safe for hosted deploys (TOS + account-ban risk).

## What shipped

- Phase 1 (1.5h): Config flags + scaffolding under `config/defaults.py` (`flowkit_*` family) and module skeletons.
- Phase 2 (4h): Chrome Extension MV3 under `flowkit_extension/` — Flow tab attach, request signer, callback poster.
- Phase 3 (3.5h): Backend `FlowService` with SQLite job queue at `data/flowkit/jobs.db`, adaptive worker pool.
- Phase 4 (2.5h): WebSocket router `/api/ws/flowkit` (reuses port 7860) + `/api/ext/callback` with optional HMAC.
- Phase 5 (3h): `ImageGenerator` flowkit provider + Gemini cinematic prompt-refiner (toggle: `flowkit_use_refiner`).
- Phase 6 (2.5h): Frontend `FlowkitSettings` panel, risk-ack validator, `docs/flowkit-integration.md` runbook.
- Tests: 43/43 passing in `tests/test_flowkit.py` (+5 added this sprint covering risk-ack validator, persistence, GET roundtrip).
- Final commits: `c4adeaa` (phase 6), `9ba4cad` (phase 5), `08799be` (phase 4).

## Key decisions

- Hard gate: `PUT /api/config` rejects `image_provider=flowkit + flowkit_enabled=true` unless `flowkit_risk_acknowledged=true`. Validator is server-side, not just UI.
- Adaptive worker ramp: starts at 1, ramps to `flowkit_concurrent_workers_max` (default 4) after `flowkit_workers_ramp_threshold` consecutive successes. Any 429/captcha/timeout resets to 1.
- WS reuses the FastAPI port — no second uvicorn process, single mount point.
- GCS signed URLs expire ~1h, so the backend `httpx`-downloads artifacts immediately on `/api/ext/callback` rather than persisting the URL.
- Per-session output dirs: `output/images/{slug}_{sid}/` for traceability and easy cleanup.
- New env var `FLOWKIT_BROWSER_API_KEY` (referer-restricted Google Labs key, capture via Extension or DevTools).
- Refiner runs Gemini before Imagen by default — `flowkit_use_refiner=True`.
- `flowkit_request_timeout` floor enforced at 30s to avoid premature bridge timeouts.

## Risks / Open items

- `IMAGE_INPUT_TYPE_CHARACTER` / `_STYLE` enum names unconfirmed against live Flow protocol — gated behind `flowkit_image_input_type_split=False` until a live network sniff confirms.
- Veo progress is poll-only at `flowkit_veo_poll_interval=5.0s`; WS-push deferred to V2.
- CAPTCHA v2 escalation requires manual solve in the attached Flow tab — no automated bypass; surfaced in extension UI.
- Account-ban risk inherent to driving consumer Google Labs sessions; `flowkit_account_warning_shown` flag surfaces a one-time warning per session.
- Local-only by design. Do not enable in hosted/multi-tenant deploys.

## Links

- Plan: `plans/260520-2358-flowkit-integration/plan.md`
- Runbook: `docs/flowkit-integration.md`
- Config flags table: `CLAUDE.md` → "Flowkit (Chrome Extension + Google Labs proxy)"
- Tests: `tests/test_flowkit.py`
