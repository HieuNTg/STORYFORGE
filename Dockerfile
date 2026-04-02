# ── Stage 1: Builder ──
FROM python:3.10-slim AS builder

WORKDIR /build

# Install build deps needed for binary wheels (cryptography, bcrypt, chromadb)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps into /build/deps
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/build/deps -r requirements.txt

# Download font (non-fatal)
RUN mkdir -p /build/fonts && curl -fsSL \
    "https://raw.githubusercontent.com/google/fonts/main/ofl/notosans/NotoSans%5Bwdth%2Cwght%5D.ttf" \
    -o /build/fonts/NotoSans-Regular.ttf \
    || echo "WARNING: Font download failed"

# ── Stage 2: Frontend build ──
FROM node:22-slim AS frontend

WORKDIR /frontend

COPY package.json package-lock.json* ./
RUN npm ci --production=false

COPY vite.config.js tailwind.config.js postcss.config.js ./
COPY web/ ./web/

RUN npm run build

# ── Stage 3: Runtime ──
FROM python:3.10-slim

WORKDIR /app

# Runtime-only system deps — keep ffmpeg, drop everything else
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /build/deps /usr/local

# Copy fonts
COPY --from=builder /build/fonts/ /app/assets/fonts/

# Copy application code (respects .dockerignore)
COPY . .

# Copy built frontend assets
COPY --from=frontend /frontend/web/dist/ /app/web/dist/

# Create required runtime directories
RUN mkdir -p data output assets/fonts data/users data/shares data/templates

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7860/api/health')" || exit 1

CMD ["python", "app.py"]
