# Self-Hosting StoryForge

This guide covers every way to run StoryForge on your own machine or server.

---

## Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| RAM | 2 GB | 4 GB |
| Disk | 2 GB free | 5 GB free |
| OS | Linux, macOS, Windows 10+ | Linux (Ubuntu 22+) |
| Runtime | Docker 20+ **or** Python 3.10+ | Docker |
| LLM | API key or local Ollama | OpenAI / Gemini |

---

## Option 1: Docker (Recommended)

Docker is the easiest path — no Python environment to manage, fonts included, single command to update.

### Quick Start (3 commands)

```bash
git clone https://github.com/your-org/storyforge.git
cd storyforge
bash scripts/setup-docker.sh
```

The setup script will prompt for your API key, build the image, and open the app at **http://localhost:7860**.

### Manual Docker Start

```bash
cp .env.example .env
# Edit .env: set STORYFORGE_API_KEY, STORYFORGE_MODEL, etc.
docker compose up -d --build
```

### Environment Variables

All configuration is done through environment variables (set in `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `STORYFORGE_API_KEY` | _(empty)_ | LLM provider API key |
| `STORYFORGE_BASE_URL` | `https://api.openai.com/v1` | LLM API endpoint |
| `STORYFORGE_MODEL` | `gpt-4o-mini` | Default model name |
| `STORYFORGE_BACKEND` | `api` | `api` for REST providers, `web` for DeepSeek browser auth |
| `STORYFORGE_TEMPERATURE` | `0.8` | Generation creativity (0.0–1.0) |
| `STORYFORGE_IMAGE_PROVIDER` | `none` | Image backend: `none`, `dalle`, `replicate`, `seedream` |
| `IMAGE_API_KEY` | _(empty)_ | API key for image provider |
| `IMAGE_API_URL` | _(empty)_ | Custom image API endpoint |
| `STORYFORGE_SECRET_KEY` | _(empty)_ | Fernet key for encrypting stored credentials at rest |

### Persistent Data

The `docker-compose.yml` mounts three host directories so your stories survive container restarts:

```yaml
volumes:
  - ./data:/app/data      # config, cache, user data
  - ./output:/app/output  # generated stories (TXT, MD, HTML, ZIP)
  - ./assets:/app/assets  # fonts, custom assets
```

Back up the `data/` and `output/` directories to preserve your work.

### Updating to a New Version

```bash
git pull
docker compose down
docker compose up -d --build
```

Your data is preserved in the mounted volumes.

---

## Option 2: Local Python Installation

Use this option when you want to develop, modify, or run without Docker.

### Setup

```bash
git clone https://github.com/your-org/storyforge.git
cd storyforge
bash scripts/setup.sh
```

The script creates a virtual environment, installs all dependencies, downloads the NotoSans font, and copies `.env.example` to `.env`.

### Manual Setup

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API key
python app.py
```

### Frontend Build (Optional)

The repository ships with pre-built frontend assets. Rebuild only if you modify `web/` sources:

```bash
# Requires Node.js 22+
npm ci
npm run build
```

---

## Option 3: Production Deployment

For a public-facing or team deployment, use additional infrastructure components.

### docker-compose.production.yml

Create a `docker-compose.production.yml` alongside the existing file:

```yaml
version: "3.8"

services:
  storyforge:
    build: .
    restart: always
    environment:
      - STORYFORGE_API_KEY=${STORYFORGE_API_KEY}
      - STORYFORGE_SECRET_KEY=${STORYFORGE_SECRET_KEY}
    volumes:
      - storyforge_data:/app/data
      - storyforge_output:/app/output
    depends_on:
      - redis

  redis:
    image: redis:7-alpine
    restart: always
    volumes:
      - redis_data:/data

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - ./certs:/etc/nginx/certs:ro
    depends_on:
      - storyforge

volumes:
  storyforge_data:
  storyforge_output:
  redis_data:
```

### TLS / SSL

Use Let's Encrypt with Certbot or provide your own certificates:

```bash
certbot certonly --standalone -d yourdomain.com
# Certificates land in /etc/letsencrypt/live/yourdomain.com/
```

Point your `nginx.conf` at the cert files. The app itself does not handle TLS — Nginx terminates it.

### Backup

Run `scripts/backup.sh` on a cron schedule to archive `data/` and `output/`:

```bash
# Example: daily backup at 2am
0 2 * * * /path/to/storyforge/scripts/backup.sh
```

---

## LLM Provider Setup

StoryForge works with any OpenAI-compatible API. Configure `.env` for your provider.

### OpenAI

```env
STORYFORGE_API_KEY=sk-...
STORYFORGE_BASE_URL=https://api.openai.com/v1
STORYFORGE_MODEL=gpt-4o-mini
```

Get a key at https://platform.openai.com/api-keys

### Google Gemini

```env
STORYFORGE_API_KEY=AIza...
STORYFORGE_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
STORYFORGE_MODEL=gemini-2.0-flash
```

Get a key at https://aistudio.google.com/app/apikey

### Anthropic Claude

```env
STORYFORGE_API_KEY=sk-ant-...
STORYFORGE_BASE_URL=https://api.anthropic.com/v1
STORYFORGE_MODEL=claude-3-haiku-20240307
```

Get a key at https://console.anthropic.com/settings/keys

### OpenRouter (Free Models Available)

```env
STORYFORGE_API_KEY=sk-or-...
STORYFORGE_BASE_URL=https://openrouter.ai/api/v1
STORYFORGE_MODEL=mistralai/mistral-7b-instruct:free
```

Get a key at https://openrouter.ai/keys — free-tier models work for testing.

### Ollama (Local, No API Key)

Run models entirely on your machine:

```bash
# Install Ollama: https://ollama.com
ollama pull llama3.2        # or mistral, qwen2.5, etc.
ollama serve                # starts on http://localhost:11434
```

```env
STORYFORGE_API_KEY=ollama
STORYFORGE_BASE_URL=http://localhost:11434/v1
STORYFORGE_MODEL=llama3.2
STORYFORGE_BACKEND=api
```

No API costs. Quality depends on your hardware and chosen model.

---

## Troubleshooting

**Port 7860 already in use**

```bash
# Find what is using the port
lsof -i :7860          # macOS/Linux
netstat -ano | findstr 7860   # Windows

# Or run on a different port
GRADIO_SERVER_PORT=7861 python app.py
```

**Font not found / boxes in PDF**

```bash
bash scripts/download-fonts.sh
```

The NotoSans font must be at `assets/fonts/NotoSans-Regular.ttf` for Vietnamese PDF export.

**LLM connection errors**

- Verify `STORYFORGE_API_KEY` is set and not expired
- Check `STORYFORGE_BASE_URL` matches your provider exactly (no trailing slash needed)
- Test connectivity: `curl -H "Authorization: Bearer $STORYFORGE_API_KEY" $STORYFORGE_BASE_URL/models`
- For Ollama: confirm `ollama serve` is running before starting StoryForge

**Docker memory issues (chromadb / sentence-transformers)**

Increase Docker Desktop memory limit:
- Docker Desktop → Settings → Resources → Memory → set to 4 GB+

Or disable RAG in the Settings tab (RAG Knowledge Base toggle) to avoid loading the embedding model.

**Container exits immediately**

```bash
docker compose logs storyforge
```

Common cause: missing `STORYFORGE_API_KEY` when `STORYFORGE_BACKEND=api`.
