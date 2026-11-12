# Self-hosting StoryForge

StoryForge runs on your own machine with Docker. This guide covers install, update, backups, exposing it to your LAN, local models and common problems. Settings, API keys and stories never leave your machine except for the calls you make to your LLM provider.

## Requirements

- Docker Desktop (Windows, macOS) or Docker Engine (Linux), with Compose v2 (`docker compose`, not `docker-compose`).
- About 4 GB of free disk for the images, plus room for your stories and images.
- RAM: 4 GB available to Docker is enough to run; building the web image needs more (see Troubleshooting).
- Network access at build time: the web build downloads fonts from Google Fonts, and the images pull base layers.
- An API key for an OpenAI-compatible LLM provider, or a local model server (see Local LLMs).

## Install and update

```bash
git clone <this repository's URL>
cd STORYFORGE
docker compose up -d --build
```

Open http://localhost:3001 and enter your API key in Settings. The API listens on http://localhost:7860. Both ports are published on `127.0.0.1` only.

Update:

```bash
git pull && docker compose up -d --build
```

To run prebuilt images instead of building (once releases are published), use `compose.release.yaml` and name the version:

```bash
STORYFORGE_VERSION=x.y.z docker compose -f compose.release.yaml up -d
```

Both files use the same volumes, so you can switch between them without losing data.

## Where your data lives

| Volume | Mounted at | Contents |
| --- | --- | --- |
| `storyforge-data` | `/app/data` | `storyforge.db` (stories), `config.json` (settings), `.secret_key`, caches, logs |
| `storyforge-output` | `/app/output` | generated images and exports |

`.secret_key` is the encryption key for the API keys saved in `config.json`. Back the two up together: with `config.json` but without `.secret_key`, your saved API keys cannot be read and you must enter them again.

## Backup and restore

The volumes have fixed names (`storyforge-data`, `storyforge-output`) in both compose files, whatever directory you cloned into. Run these from the directory where you want the archives (they are written to the current directory). Stop the stack first for a consistent copy of the database:

```bash
docker compose stop
docker run --rm -v storyforge-data:/d -v "$PWD":/b alpine tar czf /b/data.tgz -C /d .
docker run --rm -v storyforge-output:/d -v "$PWD":/b alpine tar czf /b/output.tgz -C /d .
docker compose start
```

Restore into the same (or fresh) volumes:

```bash
docker compose stop
docker run --rm -v storyforge-data:/d -v "$PWD":/b alpine sh -c "cd /d && tar xzf /b/data.tgz"
docker run --rm -v storyforge-output:/d -v "$PWD":/b alpine sh -c "cd /d && tar xzf /b/output.tgz"
docker compose start
```

On Windows:

- Git Bash rewrites paths such as `/d` and `/b`. Prefix each `docker run` with `MSYS_NO_PATHCONV=1`, for example `MSYS_NO_PATHCONV=1 docker run --rm -v storyforge-data:/d -v "$PWD":/b alpine tar czf /b/data.tgz -C /d .`.
- PowerShell: use `${PWD}` instead of `$PWD` (`-v "${PWD}:/b"`), for example `docker run --rm -v storyforge-data:/d -v "${PWD}:/b" alpine tar czf /b/data.tgz -C /d .`. For restore, keep the `sh -c "..."` argument as is.
- WSL needs no changes.

## Reset

```bash
docker compose down -v
```

This deletes both volumes: all stories, settings, saved API keys and the encryption key. Back up first if you may want anything back. `docker compose down` without `-v` only stops and removes the containers.

## Exposing StoryForge to your LAN

By default only the machine itself can reach StoryForge. To let other devices on your network use it, do all of the following. Do not skip the token.

1. Create `compose.override.yaml` next to `compose.yaml`. Publish only the web port: the browser talks to port 3001 and the web server forwards API calls internally, so the API (7860) stays on `127.0.0.1`. Compose appends to port lists, so use `!override` (Compose 2.24 or newer) to replace them:

   ```yaml
   services:
     api:
       environment:
         STORYFORGE_ACCESS_TOKEN: choose-a-long-random-token
         STORYFORGE_ALLOWED_ORIGINS: http://192.168.1.20:3001
     web:
       ports: !override ["0.0.0.0:3001:3000"]
   ```

2. `STORYFORGE_ACCESS_TOKEN` makes every API call require the token. The UI shows an unlock screen and keeps you signed in with an httponly session cookie.
3. `STORYFORGE_ALLOWED_ORIGINS` takes full origins, comma-separated: put the address you type in the browser, e.g. `http://192.168.1.20:3001` or `http://storyforge.lan:3001`. It adds to the built-in `localhost` origins. It is required: the API refuses requests whose browser host (`X-Forwarded-Host`, set by the web server) is not trusted, and writes whose `Origin` is not allowed. The host name of each origin listed here is trusted automatically.
4. Only if you also publish the API port 7860 and call it directly, add the name or IP to `STORYFORGE_ALLOWED_HOSTS` (host names or IPs only, comma-separated, no ports or wildcards).
5. Apply with `docker compose up -d`. Compose loads `compose.override.yaml` automatically only when you do not pass `-f`; with the prebuilt images pass both files: `STORYFORGE_VERSION=x.y.z docker compose -f compose.release.yaml -f compose.override.yaml up -d`.

Sessions are not individually revocable. To sign everyone out, change the token and restart.

StoryForge is not hardened for the open internet. Do not port-forward it; if you need remote access, use a VPN.

## Local LLMs

Containers reach services on your host through `host.docker.internal` (compose.yaml maps it for Linux too). For Ollama running on the host, in Settings choose an OpenAI-compatible provider and set the base URL to:

```
http://host.docker.internal:11434/v1
```

Use any non-empty API key (Ollama ignores it) and the model name you pulled, for example `llama3.1`. On Linux, make sure Ollama listens on an address the Docker bridge can reach (`OLLAMA_HOST=0.0.0.0`). LM Studio and other OpenAI-compatible servers work the same way with their own port. A server on another machine of your LAN needs `STORYFORGE_ALLOW_PRIVATE_BASE_URL=1` on the `api` service. Small local models write noticeably weaker stories and are slow; expect long runs.

## Troubleshooting

- **Port already in use.** Another program holds 3001 or 7860. Stop it, or change the left-hand number in a `compose.override.yaml` with `ports: !override ["127.0.0.1:3002:3000"]`. A web port other than 3001 is a new origin: also set `STORYFORGE_ALLOWED_ORIGINS: http://localhost:3002` on the `api` service, or saving and generating fail with 403.
- **The web build is killed or fails with out-of-memory.** Raise the memory available to Docker (Docker Desktop, Settings, Resources) to at least 6 GB, then rebuild.
- **The web build fails to download fonts.** The build needs internet access to Google Fonts. Check your proxy or VPN.
- **Windows: the build fails with path errors.** Run `docker compose` from a shell whose current directory uses an uppercase drive letter, for example `C:\Users\you\STORYFORGE`. A lowercase `c:\...` path breaks the builder.
- **Progress stops updating (SSE stalls) when another reverse proxy sits in front.** Turn off response buffering for StoryForge in that proxy. For nginx: `proxy_buffering off;` and a long `proxy_read_timeout`.
- **400 `Invalid host header` or 403 `origin_not_allowed`.** The address in your browser's bar is not trusted. Add that exact origin (scheme, host and port, e.g. `http://192.168.1.20:3001`) to `STORYFORGE_ALLOWED_ORIGINS` on the `api` service; its host name is then trusted too. This also applies behind your own reverse proxy (use the public origin, e.g. `https://storyforge.example`) and to a changed web port. If you call the API port 7860 directly, add that host name to `STORYFORGE_ALLOWED_HOSTS` too.
- **Saved API keys stopped working after a restore.** `.secret_key` was not restored with `config.json`. Re-enter the keys in Settings.
- **Logs.** `docker compose logs -f api` and `docker compose logs -f web`.
