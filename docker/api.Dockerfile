# syntax=docker/dockerfile:1
#
# StoryForge API (FastAPI on :7860). Built from the repository root by
# compose.yaml; see also docker/web.Dockerfile.

# ---- build: compile every locked dependency into wheels --------------------
FROM python:3.12-slim AS build

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY requirements.lock.txt ./
# The lock pins torch==X+cpu, which only exists on the PyTorch CPU index.
RUN pip wheel --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirements.lock.txt -w /wheels

# ---- runtime: no compiler, non-root ---------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/app/data/cache/huggingface \
    STORYFORGE_BUNDLED_DATA_DIR=/app/bundled

# Bind-mount the wheels instead of copying them so they never become a layer.
# --no-compile: the ~400 MB of .pyc files would push the image past 2.5 GB;
# Python compiles modules in memory on import instead (app startup is
# unaffected, torch is imported lazily).
RUN --mount=type=bind,from=build,source=/wheels,target=/wheels \
    pip install --no-index --no-compile /wheels/*
RUN python -m spacy download xx_ent_wiki_sm

RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin storyforge

WORKDIR /app
COPY app.py mcp_server.py ./
COPY api/ api/
COPY config/ config/
COPY errors/ errors/
COPY locales/ locales/
COPY middleware/ middleware/
COPY models/ models/
COPY pipeline/ pipeline/
COPY plugins/ plugins/
COPY services/ services/
# The comic page compositor loads its default font from assets/fonts.
COPY assets/fonts/ assets/fonts/
# Prompts, templates and the golden eval set ship with the code. They live
# outside /app/data so the storyforge-data volume cannot hide a newer copy
# after an upgrade (services/infra/bundled_data.py).
COPY data/templates/ bundled/templates/
COPY data/prompts/ bundled/prompts/
COPY data/evals/ bundled/evals/

# /app/data and /app/output are the mount points of the storyforge-data and
# storyforge-output volumes. A fresh named volume copies this ownership, so the
# app can create its database, secret key, config and logs there.
RUN mkdir -p /app/data /app/output \
    && chown 10001:10001 /app/data /app/output

USER storyforge
EXPOSE 7860
CMD ["python", "app.py"]
