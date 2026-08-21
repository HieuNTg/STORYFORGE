# Qwen Local Proxy (image provider)

`image_provider = "qwen-local"` generates panels through a **separate local
server** that speaks the OpenAI image API and drives `chat.qwen.ai` behind the
scenes. StoryForge only ever talks to that proxy over plain HTTP — it holds no
Qwen credentials of its own.

Unlike every other provider here, this one can **edit an existing image**, which
is what gives character references real weight: the reference is sent along and
modified, instead of being re-described in words and re-imagined from scratch.

> Local-only, like FlowKit: the proxy runs on the same machine (or LAN) and
> keeps a logged-in Qwen browser session. It is a reverse-engineered wrapper
> around a web app, not an official API.

## 1. Start the proxy

The proxy lives in its own repo (`Gemini-API`), and its `server/README.md` is
the source of truth. In short:

```powershell
pip install -r requirements-server.txt
python -m server.doctor --fix   # verify deps, browser driver, tokens
python -m server.main           # serves http://localhost:8000
```

Check it before touching StoryForge:

```bash
curl http://localhost:8000/health
# {"status":"ok","providers":{"qwen":true,"gemini":true}, ...}
```

`providers.qwen` must be `true`. If it is `false` the proxy is up but its Qwen
transport never started (expired token, or the browser profile is not logged
in) — image requests would fail one by one.

## 2. Point StoryForge at it

**Settings → Chung → Provider hình ảnh → `qwen-local`.** A panel appears with:

| Field | Config key | Notes |
| --- | --- | --- |
| Base URL | `qwen_local_base_url` | Default `http://localhost:8000/v1`. Empty = provider off |
| API key | `qwen_local_api_key` | Must match the proxy's `GEMINI_API_KEYS`. Stored encrypted, returned masked |
| Model ảnh | `qwen_local_model` | Empty = whatever the proxy has as `QWEN_IMAGE_MODEL` |
| Tỉ lệ khung | `qwen_local_size` | `1:1 4:3 3:4 16:9 9:16 3:2 2:3`, or empty for the proxy default |
| Timeout | `qwen_local_timeout` | Seconds. One image takes ~25–40s |
| Dùng chế độ sửa ảnh cho ảnh tham chiếu | `qwen_local_use_edit_for_refs` | See below |

The badge next to the title probes `GET /api/config/qwen-local/status`, which
reports `reachable` (proxy answers) and `qwen_ready` (its Qwen provider came
up). It does **not** poll on a timer — press *Kiểm tra lại* after starting the
proxy.

Everything is settable without the UI too:

```bash
QWEN_LOCAL_BASE_URL=http://10.0.0.5:8000/v1
QWEN_LOCAL_API_KEY=changeme-internal-key
QWEN_LOCAL_MODEL=qwen3.8-max-image
```

## 3. Aspect ratio, not pixel size

Qwen takes a ratio. StoryForge's internal callers pass pixel sizes like
`1024x1024`; those are forwarded and the proxy snaps them to the nearest
supported ratio (`1024x768` → `4:3`). Setting *Tỉ lệ khung* overrides nothing
per call — it is the default used when a caller does not specify one.

## 4. Reference images (character consistency)

When a panel has character reference images and
`qwen_local_use_edit_for_refs` is on (default), the first reference is uploaded
to the proxy's `/v1/images/qwen/edits` endpoint and edited by the panel prompt.
Qwen's edit mode takes exactly **one** source image, so any extras are ignored
rather than blended — that is logged, not silent.

Turn the toggle off to always generate text-only: faster and freer
compositionally, but the character's face drifts between panels.

Character *reference portraits* themselves (the avatars generated before
panels) also route through this provider, saved to
`output/characters/<name>_reference.png` like Seedream's.

## 5. Failure behaviour

Every failure path returns `None` and logs the reason — a dead proxy, an HTTP
error, an empty response, an oversized reference (>10 MB → falls back to
text-only), a missing reference file (→ text-only). Nothing raises into the
pipeline, so a panel is skipped rather than the run dying. `panel_retry_attempts`
still applies.

## 6. Tests

- `tests/test_qwen_local_provider.py` — client request shape, save path, every
  failure mode, `ImageGenerator` routing, `ImageProvider` gating
- `frontend/lib/schemas/config.test.ts` — schema/enum contract
- `frontend/tests/e2e/settings-qwen-local.spec.ts` — the panel renders, the
  badge reflects the probe, and Save sends only the touched fields
