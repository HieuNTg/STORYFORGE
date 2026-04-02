#!/bin/bash
set -euo pipefail

# ── StoryForge Rollback Script ──
# Usage: ./rollback.sh [commits_back]
#   commits_back  Number of commits to roll back (default: 1)

STEPS="${1:-1}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.production.yml}"
APP_SERVICE="${APP_SERVICE:-app}"
HEALTH_URL="${HEALTH_URL:-http://localhost:7860/api/health}"
HEALTH_RETRIES=20
HEALTH_INTERVAL=5

log()     { echo "[$(date '+%H:%M:%S')] $*"; }
success() { echo "[$(date '+%H:%M:%S')] OK  $*"; }
fail()    { echo "[$(date '+%H:%M:%S')] ERR $*" >&2; }

# ── Validate argument ──
if ! [[ "$STEPS" =~ ^[1-9][0-9]*$ ]]; then
  fail "Argument must be a positive integer. Got: '${STEPS}'"
  exit 1
fi

CURRENT_REF=$(git rev-parse HEAD)
TARGET_REF=$(git rev-parse "HEAD~${STEPS}")

log "Rolling back ${STEPS} commit(s)..."
log "  From : ${CURRENT_REF:0:12}  $(git log -1 --pretty='%s' HEAD)"
log "  To   : ${TARGET_REF:0:12}  $(git log -1 --pretty='%s' HEAD~${STEPS})"

read -r -p "Proceed with rollback? [y/N] " confirm
[[ "${confirm,,}" == "y" ]] || { log "Rollback cancelled."; exit 0; }

# ── Revert to target commit ──
log "Resetting to ${TARGET_REF:0:12}..."
git reset --hard "$TARGET_REF"
success "Git reset complete"

# ── Rebuild and restart ──
log "Rebuilding Docker images..."
docker compose -f "$COMPOSE_FILE" build
log "Restarting ${APP_SERVICE}..."
docker compose -f "$COMPOSE_FILE" up -d --no-deps "$APP_SERVICE"
success "Container restarted"

# ── Health check ──
log "Verifying health at ${HEALTH_URL}..."
for i in $(seq 1 "$HEALTH_RETRIES"); do
  if curl -fsSL --max-time 5 "$HEALTH_URL" > /dev/null 2>&1; then
    success "Health check passed (attempt ${i})"
    break
  fi
  if [[ $i -eq $HEALTH_RETRIES ]]; then
    fail "Health check failed — service may be degraded"
    exit 1
  fi
  log "  Attempt ${i}/${HEALTH_RETRIES} — retrying in ${HEALTH_INTERVAL}s..."
  sleep "$HEALTH_INTERVAL"
done

# ── Summary ──
echo ""
echo "══════════════════════════════════════════"
echo "  StoryForge Rollback Summary"
echo "══════════════════════════════════════════"
echo "  Rolled back : ${STEPS} commit(s)"
echo "  Was         : ${CURRENT_REF:0:12}"
echo "  Now at      : ${TARGET_REF:0:12}"
echo "  Health      : ${HEALTH_URL}"
echo "  Time        : $(date '+%Y-%m-%d %H:%M:%S')"
echo "══════════════════════════════════════════"
