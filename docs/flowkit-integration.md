# FlowKit Integration (Google Labs / Imagen 3)

FlowKit is StoryForge's **free local image** provider: it generates Imagen 3 images through your local Google Labs session via a Chrome MV3 Extension and a WebSocket proxy. **Local-only**; not usable on hosted deploys.

> StoryForge is image-focused (consistent character portraits + scene backgrounds). FlowKit also exposes a Veo video passthrough at the code level, but video is not part of the core product flow — the steps below assume image generation.

> **Prefer no setup?** For the easiest free path with zero extension/account risk, use `image_provider = huggingface` (FLUX.1-schnell) instead — see the [Image generation table in the README](../README.md#image-generation).

## Account-Ban Risk (Read First)

Google Labs may rate-limit or suspend the Google account that powers FlowKit if it detects automated traffic. **Use a secondary Google account.** The Settings UI hard-gates the provider behind a risk-acknowledgement checkbox; the backend rejects `PUT /api/config` with `image_provider=flowkit + flowkit_enabled=true` unless `flowkit_risk_acknowledged=true`.

## Install

1. Start the backend: `python app.py` (binds `127.0.0.1:7860`).
2. Open Chrome → `chrome://extensions` → enable **Developer mode**.
3. Click **Load unpacked** → select the repo's `flowkit_extension/` folder.
4. Log in to <https://labs.google/fx/tools/flow> in the same Chrome profile.
5. In StoryForge Settings → **Provider hình ảnh** = `Flowkit (Google Labs)`.
6. Tick **"Tôi hiểu rủi ro cấm tài khoản Google"**.
7. Toggle **Bật FlowKit**, then **Lưu FlowKit**.
8. The Extension popup should show "Connected"; Settings status badge turns green ("Kết nối").

## Capture `FLOWKIT_BROWSER_API_KEY`

The Flow UI signs every Imagen/Veo request with a short-lived browser API key. The Extension captures it automatically once you load a Flow page after install. If capture stalls:

1. Open <https://labs.google/fx/tools/flow> with DevTools → Network.
2. Trigger any image gen in the Flow UI.
3. Find a request to `aisandbox-pa.googleapis.com` → copy the `?key=AIza…` query value.
4. Paste it into the Extension popup's **API key (override)** field.

## File Locations

| Path | Purpose |
|------|---------|
| `flowkit_extension/` | Chrome MV3 source (manifest, background, content scripts) |
| `services/media/flow_service.py` | WS server + adaptive worker ramp + job queue |
| `services/media/image_generator.py` | Sync→async bridge that dispatches into FlowService |
| `api/flowkit.py` | `/api/ws/flowkit`, `/api/ext/callback`, `/api/flowkit/status` |
| `data/flowkit/jobs.db` | SQLite job queue (downloaded asset paths) |
| `output/images/{slug}_{sid}/` | Per-session image output |
| `output/videos/{slug}_{sid}/` | Per-session video output |

## Config Flags

See `## Key Config Flags` in `CLAUDE.md`. The FlowKit-specific ones live in `PipelineConfig` (`config/defaults.py`).

| Flag | Default | Notes |
|------|---------|-------|
| `flowkit_enabled` | `False` | Hard-gated behind `flowkit_risk_acknowledged` |
| `flowkit_port` | `7860` | Reuses FastAPI port — do not start a second uvicorn |
| `flowkit_style_reference_path` | `""` | Absolute path to a local style ref image |
| `flowkit_use_refiner` | `True` | Refine pass doubles token cost |
| `flowkit_request_timeout` | `180.0` | Sync-bridge timeout, floor 30s |
| `flowkit_concurrent_workers_max` | `4` | Adaptive ramp ceiling |
| `flowkit_workers_ramp_threshold` | `10` | Consecutive successes before +1 worker |
| `flowkit_veo_poll_interval` | `5.0` | Veo poll cadence (V1 polling-only) |
| `flowkit_image_input_type_split` | `False` | Enable after sniffing `IMAGE_INPUT_TYPE_STYLE` / `_CHARACTER` enums |
| `flowkit_callback_hmac_required` | `False` | Enable after Extension echoes `X-Callback-Secret` |
| `flowkit_risk_acknowledged` | `False` | UI-set hard gate; do not edit `config.json` by hand |

## Troubleshooting

### Status badge stuck on "Đang kiểm tra…"
Backend running on a non-default port. Open the Extension popup and update **Backend port** to match.

### "FlowKit not ready (enabled=true, ws_connected=False)"
Extension not connected. Reload `chrome://extensions`, confirm Flow tab is open and logged in, watch the Extension's service-worker console for connect errors.

### 400 `flowkit_risk_acknowledged required when enabling flowkit`
Tick the risk-ack checkbox in Settings first; same PATCH then succeeds.

### CAPTCHA escalation to v2
Flow surfaces a challenge in the Flow tab. Solve it manually — there is no auto-solver. The Extension shows a red badge until resolved.

### GCS download fails with 403 (after ~1h)
Signed URLs expire. The backend downloads immediately on callback; if you see this, the callback was delayed. Check `data/flowkit/jobs.db` for the failing job and re-queue.

### Veo job stuck pending
Veo polling runs every `flowkit_veo_poll_interval` seconds. Check `/api/flowkit/status` for `poll_running=true`. If false, restart the backend.

## Account Policy Notes

- **Never** point FlowKit at your primary Google account.
- Keep daily volume below ~50 image gens / ~10 video gens on the secondary account.
- A `429` resets the worker ramp to 1; the engine ramps back up after `flowkit_workers_ramp_threshold` consecutive successes. Repeated `429` = lower the ceiling.
- Logging out of Flow invalidates `FLOWKIT_BROWSER_API_KEY`; re-capture after login.

## Disabling

Settings → uncheck **Bật FlowKit** → Save. The WebSocket disconnects, FlowService releases its worker ramp, and `image_provider` can be flipped back to `none` / `huggingface` / `dalle` / `seedream` without restart.
