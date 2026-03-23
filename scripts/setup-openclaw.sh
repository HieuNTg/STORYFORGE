#!/bin/bash
# Setup script cho OpenClaw Zero Token
echo "=== Cài đặt OpenClaw Zero Token ==="

# Kiểm tra Node.js
if ! command -v node &> /dev/null; then
    echo "❌ Cần cài Node.js >= 18. Xem: https://nodejs.org"
    exit 1
fi

NODE_VER=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VER" -lt 18 ]; then
    echo "❌ Node.js >= 18 cần thiết. Hiện tại: $(node -v)"
    exit 1
fi

# Kiểm tra pnpm
if ! command -v pnpm &> /dev/null; then
    echo "📦 Đang cài pnpm..."
    npm install -g pnpm
fi

cd vendor/openclaw-zero-token

echo "📦 Đang cài dependencies..."
pnpm install

echo "🔨 Đang build..."
pnpm build 2>/dev/null
pnpm ui:build 2>/dev/null

echo "✅ OpenClaw đã sẵn sàng!"
echo "📝 Tiếp theo: chạy './vendor/openclaw-zero-token/start-chrome-debug.sh' và './vendor/openclaw-zero-token/onboard.sh webauth'"
