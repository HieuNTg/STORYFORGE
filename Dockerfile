# ── Stage 1: Python dependency builder ──
FROM python:3.10-slim AS py-builder

WORKDIR /build

# Build deps for binary wheels (cryptography, bcrypt, nh3)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps into isolated prefix — exclude dev/test packages
COPY requirements.txt .
RUN grep -v -E '^(pytest|playwright)' requirements.txt > requirements-prod.txt \
    && pip install --no-cache-dir --no-compile --prefix=/build/deps -r requirements-prod.txt \
    && find /build/deps -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null; \
    find /build/deps -name '*.pyc' -delete 2>/dev/null; \
    find /build/deps -name '*.pyo' -delete 2>/dev/null; \
    find /build/deps -name '*.dist-info' -exec rm -rf {} + 2>/dev/null; \
    # Remove test directories from installed packages
    find /build/deps -type d -name 'tests' -exec rm -rf {} + 2>/dev/null; \
    find /build/deps -type d -name 'test' -exec rm -rf {} + 2>/dev/null; \
    true

# Download font (non-fatal)
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && mkdir -p /build/fonts && curl -fsSL \
    "https://raw.githubusercontent.com/google/fonts/main/ofl/notosans/NotoSans%5Bwdth%2Cwght%5D.ttf" \
    -o /build/fonts/NotoSans-Regular.ttf \
    || echo "WARNING: Font download failed" \
    && rm -rf /var/lib/apt/lists/*

# ── Stage 2: Frontend build ──
FROM node:22-alpine AS frontend

WORKDIR /frontend

COPY package.json package-lock.json* ./
RUN npm ci --production=false && npm cache clean --force

COPY vite.config.js tailwind.config.js postcss.config.js ./
COPY web/ ./web/

RUN npm run build

# ── Stage 3: Final runtime image ──
FROM python:3.10-slim AS runtime

WORKDIR /app

# Runtime system deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /tmp/* /var/tmp/*

# Copy only compiled Python packages from builder
COPY --from=py-builder /build/deps /usr/local

# Copy fonts
COPY --from=py-builder /build/fonts/ /app/assets/fonts/

# Copy application code — selective COPY instead of bulk COPY . .
# This avoids pulling in node_modules, tests, docs, screenshots, etc.
COPY app.py config.py mcp_server.py ./
COPY api/ ./api/
COPY config/ ./config/
COPY errors/ ./errors/
COPY middleware/ ./middleware/
COPY models/ ./models/
COPY pipeline/ ./pipeline/
COPY plugins/ ./plugins/
COPY services/ ./services/
COPY locales/ ./locales/
COPY data/prompts/ ./data/prompts/

# Copy frontend source (HTML, CSS, JS) + built assets overlay
COPY web/index.html web/dashboard.html ./web/
COPY web/css/ ./web/css/
COPY web/js/ ./web/js/
COPY --from=frontend /frontend/web/dist/ /app/web/dist/

# Create runtime directories
RUN mkdir -p data output assets/fonts data/users data/shares data/templates

# Non-root user
RUN groupadd -r storyforge && useradd -r -g storyforge -d /app -s /sbin/nologin storyforge \
    && chown -R storyforge:storyforge /app
USER storyforge

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7860/api/health')" || exit 1

CMD ["python", "app.py"]
