FROM python:3.10-slim

WORKDIR /app

# Install system dependencies including curl for font download and ffmpeg for video composition
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create required directories
RUN mkdir -p data output assets/fonts data/users data/shares data/templates

# Download NotoSans font for Vietnamese typography support in PDF export
RUN curl -fsSL \
    "https://raw.githubusercontent.com/google/fonts/main/ofl/notosans/NotoSans%5Bwdth%2Cwght%5D.ttf" \
    -o assets/fonts/NotoSans-Regular.ttf \
    || echo "WARNING: Font download failed - PDF Vietnamese rendering will use fallback font"

# Copy templates if not in data volume
COPY data/templates/ data/templates/ 2>/dev/null || true

EXPOSE 7860

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7860/')" || exit 1

CMD ["python", "app.py"]
