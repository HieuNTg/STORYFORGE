#!/bin/bash
# StoryForge Automated Backup Script
# Usage: ./scripts/backup.sh
# Cron example: 0 2 * * * /app/scripts/backup.sh >> /var/log/storyforge-backup.log 2>&1
#
# Retention policy:
#   - Daily backups: keep last 7
#   - Weekly backups (Sunday): keep last 4

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKUP_DIR="${PROJECT_ROOT}/backups"
DATA_DIR="${PROJECT_ROOT}/data"
OUTPUT_DIR="${PROJECT_ROOT}/output"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_NAME="storyforge_backup_${TIMESTAMP}"
BACKUP_TMP="${BACKUP_DIR}/${BACKUP_NAME}"
BACKUP_ARCHIVE="${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"

DAILY_RETENTION=7    # Keep last N daily backups
WEEKLY_RETENTION=4   # Keep last N weekly backups (created on Sundays)

# ── Helpers ───────────────────────────────────────────────────────────────────
log()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO]  $*"; }
warn() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [WARN]  $*" >&2; }
err()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $*" >&2; }

# ── Pre-flight ─────────────────────────────────────────────────────────────────
log "Starting StoryForge backup: ${BACKUP_NAME}"
mkdir -p "${BACKUP_TMP}"

# ── Component: PostgreSQL ──────────────────────────────────────────────────────
backup_postgres() {
    if command -v pg_dump &>/dev/null && [[ -n "${DATABASE_URL:-}" ]]; then
        log "Backing up PostgreSQL..."
        if pg_dump "${DATABASE_URL}" --no-password --format=custom \
            -f "${BACKUP_TMP}/postgres.dump" 2>/dev/null; then
            log "PostgreSQL backup: $(du -sh "${BACKUP_TMP}/postgres.dump" | cut -f1)"
        else
            warn "PostgreSQL dump failed — skipping (non-fatal)"
        fi
    else
        log "PostgreSQL: pg_dump not available or DATABASE_URL not set — skipping"
    fi
}

# ── Component: SQLite LLM cache ────────────────────────────────────────────────
backup_sqlite() {
    local src="${DATA_DIR}/llm_cache.db"
    if [[ -f "${src}" ]]; then
        log "Backing up SQLite cache..."
        cp "${src}" "${BACKUP_TMP}/llm_cache.db"
        log "SQLite backup: $(du -sh "${BACKUP_TMP}/llm_cache.db" | cut -f1)"
    else
        log "SQLite: ${src} not found — skipping"
    fi
}

# ── Component: Config ──────────────────────────────────────────────────────────
backup_config() {
    local src="${DATA_DIR}/config.json"
    if [[ -f "${src}" ]]; then
        log "Backing up config.json..."
        cp "${src}" "${BACKUP_TMP}/config.json"
        log "Config backup: $(du -sh "${BACKUP_TMP}/config.json" | cut -f1)"
    else
        log "Config: ${src} not found — skipping"
    fi
}

# ── Component: User data ───────────────────────────────────────────────────────
backup_users() {
    local src="${DATA_DIR}/users"
    if [[ -d "${src}" ]]; then
        log "Backing up user data..."
        tar -czf "${BACKUP_TMP}/users.tar.gz" -C "${DATA_DIR}" users/
        log "User data backup: $(du -sh "${BACKUP_TMP}/users.tar.gz" | cut -f1)"
    else
        log "Users: ${src} not found — skipping"
    fi
}

# ── Component: Stories / output ────────────────────────────────────────────────
backup_stories() {
    if [[ -d "${OUTPUT_DIR}" ]]; then
        log "Backing up stories..."
        tar -czf "${BACKUP_TMP}/output.tar.gz" -C "${PROJECT_ROOT}" output/
        log "Stories backup: $(du -sh "${BACKUP_TMP}/output.tar.gz" | cut -f1)"
    else
        log "Output: ${OUTPUT_DIR} not found — skipping"
    fi
}

# ── Run components ─────────────────────────────────────────────────────────────
backup_postgres
backup_sqlite
backup_config
backup_users
backup_stories

# ── Create final archive ───────────────────────────────────────────────────────
log "Creating final archive..."
tar -czf "${BACKUP_ARCHIVE}" -C "${BACKUP_DIR}" "${BACKUP_NAME}/"
rm -rf "${BACKUP_TMP}"

ARCHIVE_SIZE="$(du -sh "${BACKUP_ARCHIVE}" | cut -f1)"
log "Backup complete: ${BACKUP_ARCHIVE} (${ARCHIVE_SIZE})"

# ── Retention: Daily (keep last 7) ────────────────────────────────────────────
log "Applying daily retention (keep last ${DAILY_RETENTION})..."
ls -1t "${BACKUP_DIR}"/storyforge_backup_*.tar.gz 2>/dev/null \
    | tail -n "+$((DAILY_RETENTION + 1))" \
    | while read -r old_backup; do
        log "Removing old daily backup: $(basename "${old_backup}")"
        rm -f "${old_backup}"
    done

# ── Retention: Weekly (copy Sunday backups, keep last 4) ──────────────────────
if [[ "$(date +%u)" == "7" ]]; then
    WEEKLY_DIR="${BACKUP_DIR}/weekly"
    mkdir -p "${WEEKLY_DIR}"
    WEEKLY_NAME="weekly_$(date +%Y_%W).tar.gz"
    log "Sunday detected — creating weekly backup: ${WEEKLY_NAME}"
    cp "${BACKUP_ARCHIVE}" "${WEEKLY_DIR}/${WEEKLY_NAME}"

    ls -1t "${WEEKLY_DIR}"/weekly_*.tar.gz 2>/dev/null \
        | tail -n "+$((WEEKLY_RETENTION + 1))" \
        | while read -r old_weekly; do
            log "Removing old weekly backup: $(basename "${old_weekly}")"
            rm -f "${old_weekly}"
        done
fi

log "Backup finished successfully."
exit 0
