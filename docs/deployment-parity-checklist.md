# Staging / Production Deployment Parity Checklist

## Key Differences

| Concern | Staging | Production |
|---|---|---|
| Compose file | `docker-compose.staging.yml` | `docker-compose.production.yml` |
| App port | `7861:7860` (external) | internal only via nginx (80/443) |
| Env file | `.env.staging` | `.env.production` |
| PostgreSQL | not in staging compose | `postgres:16-alpine` with resource limits |
| Redis | not in staging compose | `redis:7-alpine` with resource limits |
| Nginx / TLS | not present | `nginx:1.25-alpine` + Let's Encrypt |
| Resource limits | none | cpus/memory limits on every service |
| `ENVIRONMENT` var | not set | `production` |
| `STORYFORGE_AGENT_DEBATE` | `true` | `false` (default) |

## MUST Match (parity required)

- **Image / base versions** — Dockerfile `FROM` tag must be identical in both.
- **Python runtime version** — same minor version (e.g. 3.12.x).
- **`STORYFORGE_MODEL`** — same model identifier to reproduce issues.
- **`STORYFORGE_BACKEND`** — same backend driver.
- **`STORYFORGE_QUALITY_GATE`** and **`STORYFORGE_SMART_REVISION`** — both `true` in staging to catch regressions before prod.
- **Health-check paths** — staging uses `/health`, production uses `/api/health`. These must be kept in sync with the actual app route.
- **Feature-flag env var names** — any new flag added to production must also be declared in `.env.staging`.

## CAN Differ (intentional)

- **Domains / `STORYFORGE_ALLOWED_ORIGINS`** — staging uses an internal or preview domain.
- **Secrets** — `DB_PASSWORD`, `SECRET_KEY`, `STORYFORGE_API_KEY` are environment-specific.
- **Resource limits** — staging may omit or relax limits; production must enforce them.
- **Replica count / scaling** — production may run multiple app replicas behind nginx.
- **TLS certificates** — production uses Let's Encrypt; staging may use self-signed or HTTP only.
- **Log verbosity** — staging may enable `DEBUG` level; production should use `INFO` or higher.
- **`STORYFORGE_AGENT_DEBATE`** — can remain `false` in production until feature is stable.

## Pre-deploy Checklist

- [ ] `docker-compose config` validates without errors on both files.
- [ ] All required env vars listed above are present in `.env.production`.
- [ ] Health-check endpoints return 200 within `start_period`.
- [ ] Database migrations applied before app container starts.
- [ ] Backup verified (run `scripts/backup-postgres.sh`) before any destructive migration.
