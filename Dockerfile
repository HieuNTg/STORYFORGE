FROM node:22-alpine AS frontend

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY web ./web
COPY tailwind.config.js postcss.config.cjs tsconfig.json tsconfig.build.json vite.config.js ./
RUN npm run build && npm run build:css

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-db.txt ./
RUN pip install -r requirements.txt -r requirements-db.txt

COPY . .
COPY --from=frontend /app/web/css/main.built.css ./web/css/main.built.css
COPY --from=frontend /app/web/static/css/main.built.css ./web/static/css/main.built.css
COPY --from=frontend /app/web/js ./web/js

RUN mkdir -p data output/images output/checkpoints

EXPOSE 7860
CMD ["python", "app.py"]
