#!/usr/bin/env bash
# Download Vietnamese font (NotoSans) for local development.
# Usage: bash scripts/download-fonts.sh

set -e

FONT_DIR="$(dirname "$(dirname "$0")")/assets/fonts"
FONT_FILE="$FONT_DIR/NotoSans-Regular.ttf"
FONT_URL="https://raw.githubusercontent.com/google/fonts/main/ofl/notosans/NotoSans%5Bwdth%2Cwght%5D.ttf"

mkdir -p "$FONT_DIR"

if [ -f "$FONT_FILE" ]; then
  echo "Font already exists: $FONT_FILE"
  exit 0
fi

echo "Downloading NotoSans font for Vietnamese PDF support..."
curl -fsSL "$FONT_URL" -o "$FONT_FILE"

echo "Font saved to: $FONT_FILE"
