# Sprint 7: Critical Infrastructure
**Duration:** 1 week | **Owner:** DevOps + Backend | **Priority:** CRITICAL

## Objectives
- Production-ready deployment configuration
- Database migration groundwork (JSON → PostgreSQL)
- Monitoring & alerting foundation
- Backup strategy implementation

## Tasks

### 7.1 Production Deployment [DevOps] — 2 days
- [ ] Create `docker-compose.production.yml` with:
  - PostgreSQL 16 service
  - Redis 7 service
  - StoryForge app with production env vars
  - Nginx reverse proxy with TLS termination
  - Named volumes for data persistence
  - Resource limits (memory, CPU)
  - Restart policies
- [ ] Create `nginx/nginx.conf` for production:
  - TLS/SSL configuration (Let's Encrypt)
  - Gzip compression
  - Static file serving for frontend
  - Proxy pass to FastAPI
  - Security headers (HSTS, X-Frame-Options, CSP)
- [ ] Create deployment scripts:
  - `scripts/deploy.sh` — pull, build, restart with zero-downtime
  - `scripts/rollback.sh` — revert to previous version
  - `scripts/health-check.sh` — verify all services healthy

### 7.2 Monitoring Stack [DevOps] — 2 days
- [ ] Create `monitoring/prometheus.yml`:
  - Scrape StoryForge /api/metrics endpoint
  - Scrape Node Exporter for system metrics
  - Alert rules for: high error rate, slow response, disk usage
- [ ] Create `monitoring/alerting-rules.yml`:
  - Pipeline failure rate > 10%
  - API response time > 5s (p95)
  - Disk usage > 80%
  - LLM API errors > 5/min
- [ ] Create basic Grafana dashboard JSON:
  - API request rate & latency
  - Pipeline execution time per layer
  - LLM token usage & cost
  - Error rates by type
- [ ] Add Prometheus client to FastAPI (`/api/metrics` endpoint)

### 7.3 Database Migration Prep [Backend] — 2 days
- [ ] Design PostgreSQL schema:
  - `users` table (from data/users/*.json)
  - `stories` table (from story library)
  - `configs` table (from config.json)
  - `pipeline_runs` table (execution history)
  - `audit_logs` table
- [ ] Create `services/database.py`:
  - SQLAlchemy async engine setup
  - Connection pool configuration
  - Migration support (Alembic)
- [ ] Create initial Alembic migration
- [ ] Create `services/config_repository.py`:
  - Abstract interface for config storage
  - PostgreSQL implementation
  - JSON file fallback for local dev

### 7.4 Backup Strategy [DevOps] — 1 day
- [ ] Create `scripts/backup.sh`:
  - PostgreSQL pg_dump (when migrated)
  - SQLite backup (current)
  - JSON config files backup
  - Generated stories/exports backup
  - Upload to S3-compatible storage
- [ ] Create `scripts/restore.sh` — restore from backup
- [ ] Add cron job configuration for daily backups

## Success Criteria
- [ ] `docker-compose -f docker-compose.production.yml up` starts all services
- [ ] Health check passes for all services
- [ ] Prometheus scrapes metrics successfully
- [ ] Backup script runs without errors
- [ ] Database schema reviewed and approved

## Risks
- PostgreSQL migration is complex; Sprint 7 is PREP only, actual migration in Sprint 8
- Cloud provider not yet decided — configs should be cloud-agnostic
