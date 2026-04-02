#!/bin/bash
# StoryForge local development setup
# Usage: bash scripts/setup.sh
set -euo pipefail

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo "================================================"
echo "  StoryForge Setup"
echo "  Automated story generation pipeline"
echo "================================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# ── Prerequisites ─────────────────────────────────────────────────────────────
echo "Checking prerequisites..."

# Python 3.10+
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
  echo "ERROR: Python not found. Install Python 3.10+ from https://python.org"
  exit 1
fi

PYTHON=$(command -v python3 2>/dev/null || command -v python)
PY_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$("$PYTHON" -c "import sys; print(sys.version_info.major)")
PY_MINOR=$("$PYTHON" -c "import sys; print(sys.version_info.minor)")

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
  echo "ERROR: Python 3.10+ required, found $PY_VERSION"
  exit 1
fi
echo "  Python $PY_VERSION ... OK"

# pip
if ! "$PYTHON" -m pip --version &>/dev/null; then
  echo "ERROR: pip not available. Run: $PYTHON -m ensurepip"
  exit 1
fi
echo "  pip ... OK"

# git
if ! command -v git &>/dev/null; then
  echo "  git ... NOT FOUND (optional, needed for updates)"
else
  echo "  git $(git --version | awk '{print $3}') ... OK"
fi

# Node.js 18+ (optional, for frontend rebuild)
if command -v node &>/dev/null; then
  NODE_VERSION=$(node --version | sed 's/v//')
  NODE_MAJOR=$(echo "$NODE_VERSION" | cut -d. -f1)
  if [ "$NODE_MAJOR" -ge 18 ]; then
    echo "  Node.js v$NODE_VERSION ... OK (frontend build available)"
  else
    echo "  Node.js v$NODE_VERSION ... too old (18+ needed for frontend build, skipping)"
  fi
else
  echo "  Node.js ... NOT FOUND (optional; pre-built frontend assets included)"
fi

echo ""

# ── Virtual Environment ───────────────────────────────────────────────────────
if [ ! -d "$PROJECT_ROOT/venv" ]; then
  echo "Creating virtual environment..."
  "$PYTHON" -m venv "$PROJECT_ROOT/venv"
  echo "  venv created"
else
  echo "Virtual environment already exists, skipping creation"
fi

# Activate
if [ -f "$PROJECT_ROOT/venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$PROJECT_ROOT/venv/bin/activate"
else
  # Windows Git Bash path
  # shellcheck disable=SC1091
  source "$PROJECT_ROOT/venv/Scripts/activate"
fi
echo "  venv activated"
echo ""

# ── Python Dependencies ───────────────────────────────────────────────────────
echo "Installing Python dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r "$PROJECT_ROOT/requirements.txt"
echo "  requirements.txt installed"

if [ -f "$PROJECT_ROOT/requirements-test.txt" ]; then
  echo "Installing test dependencies..."
  pip install --quiet -r "$PROJECT_ROOT/requirements-test.txt"
  echo "  requirements-test.txt installed"
fi
echo ""

# ── Font Download ─────────────────────────────────────────────────────────────
FONT_DIR="$PROJECT_ROOT/assets/fonts"
FONT_FILE="$FONT_DIR/NotoSans-Regular.ttf"

mkdir -p "$FONT_DIR"

if [ ! -f "$FONT_FILE" ]; then
  echo "Downloading NotoSans font (Vietnamese PDF support)..."
  FONT_URL="https://raw.githubusercontent.com/google/fonts/main/ofl/notosans/NotoSans%5Bwdth%2Cwght%5D.ttf"
  if curl -fsSL "$FONT_URL" -o "$FONT_FILE" 2>/dev/null; then
    echo "  Font saved to assets/fonts/NotoSans-Regular.ttf"
  else
    echo "  WARNING: Font download failed. PDF export may show boxes for Vietnamese text."
    echo "  Run manually: bash scripts/download-fonts.sh"
  fi
else
  echo "NotoSans font already present, skipping download"
fi
echo ""

# ── Data Directories ──────────────────────────────────────────────────────────
echo "Creating data directories..."
for dir in data output data/users data/audit data/feedback data/branches data/templates; do
  mkdir -p "$PROJECT_ROOT/$dir"
done
echo "  data/ output/ data/users/ data/audit/ data/feedback/ created"
echo ""

# ── Environment File ──────────────────────────────────────────────────────────
if [ ! -f "$PROJECT_ROOT/.env" ]; then
  cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
  echo "Created .env from .env.example"
  echo "  Edit .env to set STORYFORGE_API_KEY and other settings"
else
  echo ".env already exists, skipping copy"
fi
echo ""

# ── Done ──────────────────────────────────────────────────────────────────────
echo "================================================"
echo "  Setup complete!"
echo ""
echo "  To start StoryForge:"
echo "    source venv/bin/activate"
echo "    (Windows: venv\\Scripts\\activate)"
echo "    python app.py"
echo ""
echo "  Then open: http://localhost:7860"
echo "================================================"
echo ""
