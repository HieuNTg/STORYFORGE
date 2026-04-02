#!/bin/bash
# StoryForge Docker setup
# Usage: bash scripts/setup-docker.sh
set -euo pipefail

echo ""
echo "================================================"
echo "  StoryForge Docker Setup"
echo "================================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# ── Prerequisites ─────────────────────────────────────────────────────────────
echo "Checking prerequisites..."

if ! command -v docker &>/dev/null; then
  echo "ERROR: Docker not found."
  echo "  Install from: https://docs.docker.com/get-docker/"
  exit 1
fi
echo "  Docker $(docker --version | awk '{print $3}' | tr -d ',') ... OK"

# Support both 'docker compose' (v2 plugin) and 'docker-compose' (v1 standalone)
if docker compose version &>/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose &>/dev/null; then
  COMPOSE="docker-compose"
else
  echo "ERROR: Docker Compose not found."
  echo "  Docker Desktop includes Compose. Or install: https://docs.docker.com/compose/install/"
  exit 1
fi
echo "  Docker Compose ... OK"
echo ""

# ── Environment File ──────────────────────────────────────────────────────────
if [ ! -f "$PROJECT_ROOT/.env" ]; then
  cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
  echo "Created .env from .env.example"
fi

# ── API Key ───────────────────────────────────────────────────────────────────
echo "LLM Provider Configuration"
echo "---------------------------"
echo "StoryForge needs an LLM API key to generate stories."
echo "Supported: OpenAI, Gemini, Anthropic, OpenRouter, or local Ollama."
echo ""
printf "Enter your LLM API key (or press Enter to skip for Ollama): "
read -r API_KEY

if [ -n "$API_KEY" ]; then
  # Replace the placeholder line in .env (works on both Linux and macOS)
  if grep -q "^STORYFORGE_API_KEY=" "$PROJECT_ROOT/.env"; then
    sed -i.bak "s|^STORYFORGE_API_KEY=.*|STORYFORGE_API_KEY=$API_KEY|" "$PROJECT_ROOT/.env"
    rm -f "$PROJECT_ROOT/.env.bak"
  else
    echo "STORYFORGE_API_KEY=$API_KEY" >> "$PROJECT_ROOT/.env"
  fi
  echo "  API key saved to .env"
else
  echo "  Skipped. Set STORYFORGE_API_KEY in .env later, or configure Ollama."
fi
echo ""

# ── Build and Start ───────────────────────────────────────────────────────────
echo "Building and starting StoryForge containers..."
echo "(First build downloads dependencies and may take 3-5 minutes)"
echo ""
$COMPOSE up -d --build
echo ""

# ── Health Check ─────────────────────────────────────────────────────────────
echo "Waiting for StoryForge to be ready..."
MAX_WAIT=30
WAITED=0
until curl -sf http://localhost:7860/api/health >/dev/null 2>&1; do
  if [ "$WAITED" -ge "$MAX_WAIT" ]; then
    echo ""
    echo "WARNING: Health check timed out after ${MAX_WAIT}s."
    echo "  Container may still be starting. Check logs:"
    echo "    $COMPOSE logs --tail=50 storyforge"
    break
  fi
  printf "."
  sleep 2
  WAITED=$((WAITED + 2))
done

echo ""
echo ""

# ── Done ──────────────────────────────────────────────────────────────────────
echo "================================================"
echo "  StoryForge is running!"
echo ""
echo "  Open: http://localhost:7860"
echo ""
echo "  Useful commands:"
echo "    $COMPOSE logs -f storyforge   # view logs"
echo "    $COMPOSE down                 # stop"
echo "    $COMPOSE restart storyforge   # restart"
echo "================================================"
echo ""
