#!/bin/bash
set -euo pipefail
DHPARAM_PATH="${1:-nginx/ssl/dhparam.pem}"
mkdir -p "$(dirname "$DHPARAM_PATH")"
if [ ! -f "$DHPARAM_PATH" ]; then
  echo "Generating DH parameters (2048-bit)..."
  openssl dhparam -out "$DHPARAM_PATH" 2048
  echo "Done: $DHPARAM_PATH"
else
  echo "dhparam.pem already exists at $DHPARAM_PATH"
fi
