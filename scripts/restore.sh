#!/bin/bash
# StoryForge Restore Script
# Usage: ./scripts/restore.sh <path-to-backup.tar.gz>
# Restores: PostgreSQL, SQLite, config, user data, stories

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DATA_DIR="${PROJECT_ROOT}/data"
OUTPUT_DIR="${PROJECT_ROOT}/output"
RESTORE_TMP="${PROJECT_ROOT}/backups/.restore_tmp_$$"

# ── Helpers ───────────────────────────────────────────────────────────────────
log()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO]  $*"; }
warn() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [WARN]  $*" >&2; }
err()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $*" >&2; exit 1; }

cleanup() { rm -rf "${RESTORE_TMP}"; }
trap cleanup EXIT

# ── Usage check ───────────────────────────────────────────────────────────────
if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <backup-archive.tar.gz>"
    echo ""
    echo "Available backups:"
    ls -lh "${PROJECT_ROOT}/backups/"*.tar.gz 2>/dev/null || echo "  (none found in ${PROJECT_ROOT}/backups/)"
    exit 1
fi

BACKUP_ARCHIVE="$1"

# ── Verify backup archive ──────────────────────────────────────────────────────
log "Verifying backup: ${BACKUP_ARCHIVE}"
[[ -f "${BACKUP_ARCHIVE}" ]] || err "Backup file not found: ${BACKUP_ARCHIVE}"

if ! tar -tzf "${BACKUP_ARCHIVE}" &>/dev/null; then
    err "Backup archive is corrupt or not a valid tar.gz: ${BACKUP_ARCHIVE}"
fi

ARCHIVE_SIZE="$(du -sh "${BACKUP_ARCHIVE}" | cut -f1)"
ARCHIVE_CONTENTS="$(tar -tzf "${BACKUP_ARCHIVE}" | head -20)"
log "Archive size: ${ARCHIVE_SIZE}"
log "Archive contents (first 20 entries):"
echo "${ARCHIVE_CONTENTS}" | while read -r line; do log "  ${line}"; done

# ── Confirmation prompt ────────────────────────────────────────────────────────
echo ""
echo "WARNING: This will overwrite existing data in:"
echo "  - ${DATA_DIR}/"
echo "  - ${OUTPUT_DIR}/"
if [[ -n "${DATABASE_URL:-}" ]]; then
    echo "  - PostgreSQL database (${DATABASE_URL})"
fi
echo ""
read -r -p "Type 'yes' to confirm restore: " CONFIRM
if [[ "${CONFIRM}" != "yes" ]]; then
    log "Restore cancelled by user."
    exit 0
fi

# ── Extract archive ────────────────────────────────────────────────────────────
log "Extracting backup archive..."
mkdir -p "${RESTORE_TMP}"
tar -xzf "${BACKUP_ARCHIVE}" -C "${RESTORE_TMP}" --strip-components=1

# ── Restore: PostgreSQL ────────────────────────────────────────────────────────
if [[ -f "${RESTORE_TMP}/postgres.dump" ]]; then
    if command -v pg_restore &>/dev/null && [[ -n "${DATABASE_URL:-}" ]]; then
        log "Restoring PostgreSQL..."
        pg_restore --clean --if-exists -d "${DATABASE_URL}" "${RESTORE_TMP}/postgres.dump" \
            && log "PostgreSQL restore complete." \
            || warn "PostgreSQL restore failed — check logs above."
    else
        warn "pg_restore not available or DATABASE_URL not set — skipping PostgreSQL restore."
    fi
fi

# ── Restore: SQLite ────────────────────────────────────────────────────────────
if [[ -f "${RESTORE_TMP}/llm_cache.db" ]]; then
    log "Restoring SQLite cache..."
    mkdir -p "${DATA_DIR}"
    [[ -f "${DATA_DIR}/llm_cache.db" ]] && cp "${DATA_DIR}/llm_cache.db" "${DATA_DIR}/llm_cache.db.bak"
    cp "${RESTORE_TMP}/llm_cache.db" "${DATA_DIR}/llm_cache.db"
    log "SQLite restore complete."
fi

# ── Restore: Config ────────────────────────────────────────────────────────────
if [[ -f "${RESTORE_TMP}/config.json" ]]; then
    log "Restoring config.json..."
    mkdir -p "${DATA_DIR}"
    [[ -f "${DATA_DIR}/config.json" ]] && cp "${DATA_DIR}/config.json" "${DATA_DIR}/config.json.bak"
    cp "${RESTORE_TMP}/config.json" "${DATA_DIR}/config.json"
    log "Config restore complete."
fi

# ── Restore: User data ────────────────────────────────────────────────────────
if [[ -f "${RESTORE_TMP}/users.tar.gz" ]]; then
    log "Restoring user data..."
    [[ -d "${DATA_DIR}/users" ]] && mv "${DATA_DIR}/users" "${DATA_DIR}/users.bak.$$"
    mkdir -p "${DATA_DIR}"
    tar -xzf "${RESTORE_TMP}/users.tar.gz" -C "${DATA_DIR}/"
    log "User data restore complete."
fi

# ── Restore: Stories / output ─────────────────────────────────────────────────
if [[ -f "${RESTORE_TMP}/output.tar.gz" ]]; then
    log "Restoring stories..."
    [[ -d "${OUTPUT_DIR}" ]] && mv "${OUTPUT_DIR}" "${OUTPUT_DIR}.bak.$$"
    mkdir -p "${PROJECT_ROOT}"
    tar -xzf "${RESTORE_TMP}/output.tar.gz" -C "${PROJECT_ROOT}/"
    log "Stories restore complete."
fi

log "Restore finished successfully from: ${BACKUP_ARCHIVE}"
exit 0
