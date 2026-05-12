# Production Deployment Guide

## Quick Start

StoryForge production deployment uses Docker Compose with the app, PostgreSQL,
and password-protected Redis. Metrics are exposed at `/api/metrics` and can be
scraped by an external Prometheus/Grafana stack.

```bash
# Prepare environment
cp .env.production.example .env.production
# Edit .env.production with real secrets

# Deploy
docker compose --env-file .env.production -f docker-compose.production.yml up -d
```

## Configuration

All production settings are in `.env.production` (DO NOT commit to source control):

| Variable | Purpose | Example |
|----------|---------|---------|
| `POSTGRES_PASSWORD` | PostgreSQL password | `openssl rand -base64 32` |
| `STORYFORGE_SECRET_KEY` | Config-secret encryption and signing key | `openssl rand -hex 32` |
| `STORYFORGE_AUTH_REQUIRED` | Enforce JWT/RBAC on sensitive APIs | `1` |
| `STORYFORGE_SUPERADMIN_ID` | Bootstrap superadmin user ID | `uuid-from-/api/auth/register` |
| `REDIS_PASSWORD` | Redis authentication | `openssl rand -base64 32` |
| `STORYFORGE_ALLOWED_ORIGINS` | CORS-allowed domains | `https://storyforge.example.com` |
| `STORYFORGE_API_KEY` | LLM provider API key | `sk-...` |
| `STORYFORGE_MODEL` | Default LLM model | `gpt-4o-mini` |
| `STORYFORGE_ENABLE_DOCS` | Disable public Swagger/Redoc in prod | `0` |

Sensitive values persisted through the Settings UI are encrypted in
`data/config.json` when `STORYFORGE_SECRET_KEY` is set. Without that key,
local-development installs intentionally fall back to plaintext for backwards
compatibility; do not run production that way.

## Redis Security

**P3 Sprint Update**: Redis now requires password authentication in production.

- **Command**: `redis-server --appendonly yes --appendfsync everysec --requirepass ${REDIS_PASSWORD}`
- **Connection URL**: `redis://:${REDIS_PASSWORD}@redis:6379/0`
- **Health Check**: `redis-cli -a "${REDIS_PASSWORD}" ping`

Configure a strong, random password (min 32 chars):
```bash
openssl rand -base64 32
```

## Authentication Bootstrap

Production should run with `STORYFORGE_AUTH_REQUIRED=1`. After first deploy:

1. Temporarily register a user through `/api/auth/register`.
2. Copy the returned `user_id` into `STORYFORGE_SUPERADMIN_ID`.
3. Restart the app container.

That user now receives `superadmin` permissions regardless of the stored role.

## Horizontal Scaling

Scaling is enabled via `docker compose --scale app=N`:

```bash
# Scale to 3 instances
docker compose -f docker-compose.production.yml up -d --scale app=3
```

**Requirements for multi-instance:**
- Redis configured (shared rate limiting, token revocation, session state)
- PostgreSQL with persistent volume
- A reverse proxy with sticky sessions for SSE streams

**Note**: SQLite LLM cache remains per-instance (acceptable for non-persistent cache).

## Health Check Endpoints

| Endpoint | Purpose | Critical |
|----------|---------|----------|
| `/api/health` | Shallow check (uptime, service flags) | Yes |
| `/api/health/deep` | Full subsystem probe (DB, Redis, disk, memory, LLM) | Yes |

**Scale Readiness** (from `/api/health/deep`):
```json
{
  "scale_ready": true,
  "components": {
    "database": {"status": "ok"},
    "redis": {"status": "ok"}
  }
}
```

`scale_ready=true` confirms Redis + PostgreSQL are healthy for multi-instance deployment.

## Monitoring

The production compose file exposes metrics from the app. Deploy Prometheus,
Grafana, and log aggregation separately if needed.

| Endpoint | Purpose |
|----------|---------|
| `/api/metrics` | Internal text metrics |
| `/api/metrics/prometheus` | Prometheus exposition format |

## SSL/TLS

Terminate HTTPS at your reverse proxy or load balancer. A minimal Nginx/Caddy
deployment should proxy to `http://app:7860`, preserve `X-Forwarded-Proto`,
and use sticky routing if multiple app replicas serve SSE streams.

Set `STORYFORGE_ALLOWED_ORIGINS` to the final HTTPS origin.

## Resource Limits

| Service | CPU Limit | Memory Limit |
|---------|-----------|--------------|
| App | 2.0 | 2 GB |
| PostgreSQL | 1.0 | 512 MB |
| Redis | 0.5 | 256 MB |
Resource limits are deployment-platform specific. Add `deploy.resources` in
`docker-compose.production.yml` or your orchestrator once you know the target
machine size.

## Persistence

Data volumes:
- `storyforge-pg-data` → PostgreSQL database
- `storyforge-redis-data` → Redis RDB + AOF
- `storyforge-data` → app config, JWT keys, local caches
- `storyforge-output` → generated checkpoints, exports, images

## Troubleshooting

**Redis connection fails**:
```bash
docker compose logs redis
docker compose --env-file .env.production -f docker-compose.production.yml exec redis \
  redis-cli -a "$REDIS_PASSWORD" ping
```

**Health check timeout**:
```bash
curl http://localhost:7860/api/health/deep
```

**Multi-instance routing issues**:
- Verify sticky routing in your reverse proxy/load balancer.
- Check that SSE requests keep reaching the same app replica.
