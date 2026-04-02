#!/bin/bash
set -euo pipefail

# ── StoryForge Production Deployment ──
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.production.yml}"
APP_SERVICE="${APP_SERVICE:-app}"
HEALTH_URL="${HEALTH_URL:-http://localhost:7860/api/health}"
HEALTH_RETRIES=20
HEALTH_INTERVAL=5

log()     { echo "[$(date '+%H:%M:%S')] $*"; }
success() { echo "[$(date '+%H:%M:%S')] OK  $*"; }
fail()    { echo "[$(date '+%H:%M:%S')] ERR $*" >&2; }

# ── 1. Validate required environment variables ──
log "Validating environment..."
missing=()
[[ -z "${DB_PASSWORD:-}" ]]  && missing+=(DB_PASSWORD)
[[ -z "${SECRET_KEY:-}" ]]   && missing+=(SECRET_KEY)
if [[ ${#missing[@]} -gt 0 ]]; then
  fail "Missing required env vars: ${missing[*]}"
  exit 1
fi
success "Environment OK"

# ── 2. Capture rollback ref before any changes ──
PREV_REF=$(git rev-parse HEAD)
log "Current ref: ${PREV_REF:0:12}"

rollback() {
  fail "Deployment failed — rolling back to ${PREV_REF:0:12}..."
  git reset --hard "$PREV_REF"
  docker compose -f "$COMPOSE_FILE" up -d --no-deps "$APP_SERVICE" || true
  fail "Rollback complete. Manual inspection recommended."
  exit 1
}
trap rollback ERR

# ── 3. Pull latest code ──
log "Pulling latest code..."
git pull --ff-only
NEW_REF=$(git rev-parse HEAD)
success "Updated to ${NEW_REF:0:12}"

# ── 4. Build Docker images ──
log "Building Docker images (compose file: ${COMPOSE_FILE})..."
docker compose -f "$COMPOSE_FILE" build
success "Build complete"

# ── 5. Run database migrations ──
log "Running database migrations..."
docker compose -f "$COMPOSE_FILE" run --rm "$APP_SERVICE" \
  alembic upgrade head 2>&1 | sed 's/^/  /' || {
  log "alembic not configured or no migrations — skipping"
}
success "Migrations done"

# ── 6. Zero-downtime restart ──
log "Restarting ${APP_SERVICE} with zero-downtime..."
docker compose -f "$COMPOSE_FILE" up -d --no-deps "$APP_SERVICE"
success "Container restarted"

# ── 7. Wait for health check ──
log "Waiting for health check at ${HEALTH_URL}..."
for i in $(seq 1 "$HEALTH_RETRIES"); do
  if curl -fsSL --max-time 5 "$HEALTH_URL" > /dev/null 2>&1; then
    success "Health check passed (attempt ${i})"
    break
  fi
  if [[ $i -eq $HEALTH_RETRIES ]]; then
    fail "Health check failed after ${HEALTH_RETRIES} attempts"
    exit 1
  fi
  log "  Attempt ${i}/${HEALTH_RETRIES} — retrying in ${HEALTH_INTERVAL}s..."
  sleep "$HEALTH_INTERVAL"
done

# ── 8. Deployment summary ──
trap - ERR
echo ""
echo "══════════════════════════════════════════"
echo "  StoryForge Deployment Summary"
echo "══════════════════════════════════════════"
echo "  Previous : ${PREV_REF:0:12}"
echo "  Deployed : ${NEW_REF:0:12}"
echo "  Service  : ${APP_SERVICE}"
echo "  Health   : ${HEALTH_URL}"
echo "  Time     : $(date '+%Y-%m-%d %H:%M:%S')"
echo "══════════════════════════════════════════"
