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

RUN mkdir -p data output/images output/checkpoints

EXPOSE 7860
CMD ["python", "app.py"]
