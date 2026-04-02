#!/bin/bash
# StoryForge PostgreSQL Backup Script
#
# Uses pg_dump with gzip compression, rotates backups automatically.
#
# Configuration (environment variables):
#   DB_HOST      — PostgreSQL hostname           (default: localhost)
#   DB_PORT      — PostgreSQL port               (default: 5432)
#   DB_NAME      — Database name                 (default: storyforge)
#   DB_USER      — Database user                 (default: storyforge)
#   PGPASSWORD   — Password (standard pg env var; or use .pgpass)
#   BACKUP_DIR   — Directory to store backups    (default: /var/backups/storyforge/postgres)
#
# Retention policy:
#   Daily  — keep last 7 backups
#   Weekly — keep last 4 (created on Sundays, stored in $BACKUP_DIR/weekly/)
#
# Cron setup (run daily at 02:00):
#   0 2 * * * DB_HOST=postgres DB_NAME=storyforge DB_USER=storyforge \
#             PGPASSWORD=secret BACKUP_DIR=/var/backups/storyforge/postgres \
#             /app/scripts/backup-postgres.sh >> /var/log/storyforge-pg-backup.log 2>&1
#
# Return codes:
#   0 — success
#   1 — pg_dump not found
#   2 — pg_dump failed
#   3 — backup directory could not be created

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-storyforge}"
DB_USER="${DB_USER:-storyforge}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/storyforge/postgres}"

DAILY_RETENTION="${DAILY_RETENTION:-7}"
WEEKLY_RETENTION="${WEEKLY_RETENTION:-4}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.dump.gz"

# ── Helpers ───────────────────────────────────────────────────────────────────
log()  { printf '[%s] [INFO]  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
warn() { printf '[%s] [WARN]  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2; }
err()  { printf '[%s] [ERROR] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2; }

# ── Pre-flight checks ─────────────────────────────────────────────────────────
if ! command -v pg_dump &>/dev/null; then
    err "pg_dump not found in PATH. Install postgresql-client and retry."
    exit 1
fi

if ! mkdir -p "${BACKUP_DIR}"; then
    err "Cannot create backup directory: ${BACKUP_DIR}"
    exit 3
fi

log "Starting PostgreSQL backup: host=${DB_HOST}:${DB_PORT} db=${DB_NAME} user=${DB_USER}"
log "Output: ${BACKUP_FILE}"

# ── pg_dump ───────────────────────────────────────────────────────────────────
# --format=custom produces a compressed, parallel-restore-capable archive.
# We pipe through gzip for an additional .gz wrapper so the file is readable
# by standard tools (zcat/zless) without pg_restore.
if ! pg_dump \
        --host="${DB_HOST}" \
        --port="${DB_PORT}" \
        --username="${DB_USER}" \
        --dbname="${DB_NAME}" \
        --format=plain \
        --no-password \
    | gzip -9 > "${BACKUP_FILE}"; then
    err "pg_dump failed — removing partial file."
    rm -f "${BACKUP_FILE}"
    exit 2
fi

BACKUP_SIZE="$(du -sh "${BACKUP_FILE}" | cut -f1)"
log "Backup complete: ${BACKUP_FILE} (${BACKUP_SIZE})"

# ── Retention: daily (keep last N) ───────────────────────────────────────────
log "Applying daily retention (keep last ${DAILY_RETENTION})..."
ls -1t "${BACKUP_DIR}"/"${DB_NAME}"_*.dump.gz 2>/dev/null \
    | tail -n "+$((DAILY_RETENTION + 1))" \
    | while IFS= read -r old; do
        log "Removing old backup: $(basename "${old}")"
        rm -f "${old}"
    done

# ── Retention: weekly (copy Sunday → weekly/, keep last N) ───────────────────
if [[ "$(date +%u)" == "7" ]]; then
    WEEKLY_DIR="${BACKUP_DIR}/weekly"
    mkdir -p "${WEEKLY_DIR}"
    WEEKLY_FILE="${WEEKLY_DIR}/${DB_NAME}_weekly_$(date +%Y_W%V).dump.gz"
    log "Sunday — promoting to weekly backup: ${WEEKLY_FILE}"
    cp "${BACKUP_FILE}" "${WEEKLY_FILE}"

    ls -1t "${WEEKLY_DIR}"/"${DB_NAME}"_weekly_*.dump.gz 2>/dev/null \
        | tail -n "+$((WEEKLY_RETENTION + 1))" \
        | while IFS= read -r old; do
            log "Removing old weekly backup: $(basename "${old}")"
            rm -f "${old}"
        done
fi

log "PostgreSQL backup finished successfully."
exit 0
