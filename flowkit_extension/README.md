# StoryForge FlowKit Extension

Local Chrome MV3 extension that proxies Google Labs Flow (Imagen 3 + Veo) to the StoryForge backend over WebSocket.

> Full integration guide: [`docs/flowkit-integration.md`](../docs/flowkit-integration.md) — install, `FLOWKIT_BROWSER_API_KEY` capture, config flags, troubleshooting, account-policy notes.

## Install

1. Open `chrome://extensions`.
2. Enable Developer Mode (top right).
3. Click "Load unpacked" and pick this `flowkit_extension/` directory.

## First Use

1. Start StoryForge: `python app.py` (listens on `127.0.0.1:7860`).
2. Open `https://labs.google/fx/tools/flow` and sign in (use a secondary Google account; automated traffic carries account-ban risk).
3. Open the extension popup — status badge should turn green within 5 s.
4. In StoryForge Settings: set `image_provider = flowkit`, tick the risk-acknowledged checkbox, save.
5. Trigger image generation — requests should stream through the popup log.

## Manual Smoke Checklist

- [ ] Load unpacked succeeds (no manifest errors in `chrome://extensions`).
- [ ] Popup opens, shows backend port 7860.
- [ ] Open Flow tab while signed in → token capture log entry appears.
- [ ] Popup status flips to `connected` once backend is running.
- [ ] Stop backend → status flips to `disconnected`; restart → reconnects within 30 s.
- [ ] Force a captcha challenge (e.g., spam 20+ generations) → red `!` badge + Toast on Flow tab.
- [ ] Change port to 7861 in popup, restart backend on that port → reconnects.

## Files

- `manifest.json` — MV3 manifest, permissions, content-script wiring.
- `background.js` — service worker: WS client, webRequest token capture, alarms, dispatcher.
- `content.js` — Toast UI + page<->background captcha bridge.
- `injected.js` — MAIN-world grecaptcha hook + fetch monkey-patch.
- `popup.html` / `popup.js` — popup UI: status badge, port input, request log.
- `rules.json` — declarativeNetRequest referer/origin rewrite.
- `icons/` — placeholder PNG icons (replace with real ones before publishing).
