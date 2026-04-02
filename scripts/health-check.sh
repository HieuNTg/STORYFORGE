#!/bin/bash
# StoryForge Production Health Check
# Usage: ./scripts/health-check.sh
# Exit 0 = all services healthy; Exit 1 = one or more services failing
#
# Checks: PostgreSQL, Redis, StoryForge app HTTP health endpoint

set -uo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
APP_HOST="${APP_HOST:-localhost}"
APP_PORT="${APP_PORT:-7860}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-storyforge}"
POSTGRES_DB="${POSTGRES_DB:-storyforge}"
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"
TIMEOUT=5   # seconds per check

# ── Counters ──────────────────────────────────────────────────────────────────
PASS=0
FAIL=0

# ── Helpers ───────────────────────────────────────────────────────────────────
check_pass() { echo "  [PASS] $*"; ((PASS++)) || true; }
check_fail() { echo "  [FAIL] $*" >&2; ((FAIL++)) || true; }

header() {
    echo ""
    echo "=== $* ==="
}

# ── PostgreSQL ────────────────────────────────────────────────────────────────
header "PostgreSQL (${POSTGRES_HOST}:${POSTGRES_PORT})"
if command -v pg_isready &>/dev/null; then
    if pg_isready -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
                  -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
                  -t "${TIMEOUT}" &>/dev/null; then
        check_pass "PostgreSQL accepting connections on ${POSTGRES_HOST}:${POSTGRES_PORT}"
    else
        check_fail "PostgreSQL not ready on ${POSTGRES_HOST}:${POSTGRES_PORT}"
    fi
elif command -v nc &>/dev/null; then
    if nc -z -w "${TIMEOUT}" "${POSTGRES_HOST}" "${POSTGRES_PORT}" 2>/dev/null; then
        check_pass "PostgreSQL port ${POSTGRES_PORT} reachable (pg_isready not installed)"
    else
        check_fail "PostgreSQL port ${POSTGRES_PORT} not reachable on ${POSTGRES_HOST}"
    fi
else
    echo "  [SKIP] pg_isready and nc not available — cannot check PostgreSQL"
fi

# ── Redis ─────────────────────────────────────────────────────────────────────
header "Redis (${REDIS_HOST}:${REDIS_PORT})"
if command -v redis-cli &>/dev/null; then
    REDIS_RESPONSE="$(redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" \
                                --no-auth-warning ping 2>/dev/null || true)"
    if [[ "${REDIS_RESPONSE}" == "PONG" ]]; then
        check_pass "Redis responded PONG on ${REDIS_HOST}:${REDIS_PORT}"
    else
        check_fail "Redis ping failed on ${REDIS_HOST}:${REDIS_PORT} (got: '${REDIS_RESPONSE}')"
    fi
elif command -v nc &>/dev/null; then
    if nc -z -w "${TIMEOUT}" "${REDIS_HOST}" "${REDIS_PORT}" 2>/dev/null; then
        check_pass "Redis port ${REDIS_PORT} reachable (redis-cli not installed)"
    else
        check_fail "Redis port ${REDIS_PORT} not reachable on ${REDIS_HOST}"
    fi
else
    echo "  [SKIP] redis-cli and nc not available — cannot check Redis"
fi

# ── StoryForge App ────────────────────────────────────────────────────────────
header "StoryForge App (${APP_HOST}:${APP_PORT}/api/health)"
HEALTH_URL="http://${APP_HOST}:${APP_PORT}/api/health"

if command -v curl &>/dev/null; then
    HTTP_STATUS="$(curl -s -o /dev/null -w "%{http_code}" \
                        --max-time "${TIMEOUT}" "${HEALTH_URL}" 2>/dev/null || echo "000")"
    if [[ "${HTTP_STATUS}" == "200" ]]; then
        BODY="$(curl -s --max-time "${TIMEOUT}" "${HEALTH_URL}" 2>/dev/null || true)"
        check_pass "App health endpoint returned 200 OK"
        echo "  Response: ${BODY}"
    else
        check_fail "App health endpoint returned HTTP ${HTTP_STATUS} (expected 200)"
    fi
elif command -v python3 &>/dev/null; then
    if python3 -c "
import urllib.request, sys
try:
    r = urllib.request.urlopen('${HEALTH_URL}', timeout=${TIMEOUT})
    sys.exit(0 if r.status == 200 else 1)
except Exception as e:
    print(e, file=sys.stderr)
    sys.exit(1)
" 2>/dev/null; then
        check_pass "App health endpoint OK"
    else
        check_fail "App health endpoint unreachable or non-200"
    fi
else
    echo "  [SKIP] curl and python3 not available — cannot check app health"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "=================================================="
echo "  Health Check Summary"
echo "=================================================="
echo "  Passed: ${PASS}"
echo "  Failed: ${FAIL}"
echo "=================================================="

if [[ "${FAIL}" -gt 0 ]]; then
    echo "  STATUS: UNHEALTHY"
    exit 1
else
    echo "  STATUS: HEALTHY"
    exit 0
fi
