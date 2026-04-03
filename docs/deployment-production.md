# Production Deployment Guide

## Quick Start

StoryForge production deployment uses Docker Compose with secure Redis, PostgreSQL, and monitoring stack.

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
| `DB_PASSWORD` | PostgreSQL password | `openssl rand -base64 32` |
| `SECRET_KEY` | JWT signing key (min 64 chars) | `openssl rand -base64 64` |
| `REDIS_PASSWORD` | Redis authentication | `openssl rand -base64 32` |
| `ALLOWED_ORIGINS` | CORS-allowed domains | `https://storyforge.example.com` |
| `STORYFORGE_API_KEY` | LLM provider API key | `sk-...` |
| `STORYFORGE_MODEL` | Default LLM model | `gpt-4o-mini` |
| `NGINX_SERVER_NAME` | TLS certificate domain | `storyforge.example.com` |

## Redis Security

**P3 Sprint Update**: Redis now requires password authentication in production.

- **Command**: `redis-server --appendonly yes --appendfsync everysec --requirepass ${REDIS_PASSWORD}`
- **Connection URL**: `redis://:${REDIS_PASSWORD}@redis:6379/0`
- **Health Check**: `redis-cli -a "${REDIS_PASSWORD}" ping`

Configure a strong, random password (min 32 chars):
```bash
openssl rand -base64 32
```

## Horizontal Scaling

Scaling is enabled via `docker compose --scale app=N`:

```bash
# Scale to 3 instances
docker compose -f docker-compose.production.yml up -d --scale app=3
```

**Requirements for multi-instance:**
- Redis configured (shared rate limiting, token revocation, session state)
- PostgreSQL with persistent volume
- Nginx sticky sessions (`ip_hash`) — ensures SSE streams route to same app instance

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

## Monitoring Stack

Included services:

| Service | Port | Purpose |
|---------|------|---------|
| Prometheus | 9090 (localhost) | Metrics collection |
| Grafana | 3000 | Dashboards & alerts |
| Loki | 3100 (localhost) | Log aggregation |
| Promtail | — | Log shipper |

**Access**:
- Grafana: `http://localhost:3000` (default: admin/storyforge)
- Prometheus: `http://localhost:9090`

## SSL/TLS

Nginx handles HTTPS with Let's Encrypt certificates (certbot auto-renewal):

```bash
# Initialize certificates (before first deployment)
certbot certonly --webroot --webroot-path ./nginx/webroot \
  -d storyforge.example.com
```

Nginx automatically redirects HTTP → HTTPS and enforces HSTS.

## Resource Limits

| Service | CPU Limit | Memory Limit |
|---------|-----------|--------------|
| App | 2.0 | 2 GB |
| PostgreSQL | 1.0 | 512 MB |
| Redis | 0.5 | 256 MB |
| Nginx | 0.5 | 128 MB |
| Loki | 0.5 | 256 MB |
| Prometheus | 0.5 | 256 MB |
| Grafana | 0.5 | 256 MB |

Adjust in `docker-compose.production.yml` under `deploy.resources.limits`.

## Persistence

Data volumes:
- `storyforge-pg-data` → PostgreSQL database
- `storyforge-redis-data` → Redis RDB + AOF
- `loki-data` → Log storage
- `/app/data`, `/app/output`, `/app/assets` → Mounted from host

## Troubleshooting

**Redis connection fails**:
```bash
docker compose logs redis
docker compose exec redis redis-cli -a "$REDIS_PASSWORD" ping
```

**Health check timeout**:
```bash
# Check individual components
curl http://localhost:7860/api/health/deep
```

**Multi-instance routing issues**:
- Verify nginx `ip_hash` directive in `/etc/nginx/nginx.conf`
- Check sticky session via browser cookies
