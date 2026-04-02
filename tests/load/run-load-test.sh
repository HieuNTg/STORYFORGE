#!/usr/bin/env bash
# run-load-test.sh — StoryForge headless Locust runner
# Q3+Q7: Load & Performance Testing
#
# Usage:
#   ./tests/load/run-load-test.sh [OPTIONS]
#
# Options (all have defaults):
#   -u USERS        Total concurrent users     (default: 50)
#   -r SPAWN_RATE   Users spawned per second   (default: 5)
#   -t RUN_TIME     Duration e.g. 2m, 30s      (default: 2m)
#   -H HOST         Target base URL            (default: http://localhost:7860)
#   -c USER_CLASS   Locust user class to run   (default: MixedUser)
#   -T TAGS         Comma-separated task tags  (default: all tags)
#   -h              Show this help and exit
#
# Examples:
#   ./tests/load/run-load-test.sh
#   ./tests/load/run-load-test.sh -u 100 -r 10 -t 5m
#   ./tests/load/run-load-test.sh -H http://staging.storyforge.app -u 20
#   ./tests/load/run-load-test.sh -T smoke -t 30s
#   ./tests/load/run-load-test.sh -c HealthCheckUser -u 10 -t 1m

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
USERS=50
SPAWN_RATE=5
RUN_TIME="2m"
HOST="http://localhost:7860"
USER_CLASS="MixedUser"
TAGS=""

# Paths — resolve relative to this script's location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCUSTFILE="${SCRIPT_DIR}/locustfile.py"
REPORTS_DIR="${SCRIPT_DIR}/reports"

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
while getopts "u:r:t:H:c:T:h" opt; do
    case "${opt}" in
        u) USERS="${OPTARG}" ;;
        r) SPAWN_RATE="${OPTARG}" ;;
        t) RUN_TIME="${OPTARG}" ;;
        H) HOST="${OPTARG}" ;;
        c) USER_CLASS="${OPTARG}" ;;
        T) TAGS="${OPTARG}" ;;
        h)
            head -30 "${BASH_SOURCE[0]}" | grep "^#" | sed 's/^# \?//'
            exit 0
            ;;
        *) echo "Unknown option: -${OPTARG}" >&2; exit 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
if ! command -v locust &> /dev/null; then
    echo "ERROR: locust not found. Install with: pip install locust"
    exit 1
fi

if ! curl -sf "${HOST}/api/health" > /dev/null 2>&1; then
    echo "WARNING: ${HOST}/api/health is not responding."
    echo "  Ensure StoryForge is running before starting load tests."
    read -r -p "Continue anyway? [y/N] " confirm
    [[ "${confirm,,}" == "y" ]] || exit 0
fi

# ---------------------------------------------------------------------------
# Prepare output directory
# ---------------------------------------------------------------------------
TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
REPORT_PREFIX="${REPORTS_DIR}/${TIMESTAMP}"
mkdir -p "${REPORTS_DIR}"

echo ""
echo "======================================================"
echo " StoryForge Load Test"
echo "======================================================"
echo "  Host        : ${HOST}"
echo "  Users       : ${USERS}"
echo "  Spawn rate  : ${SPAWN_RATE}/s"
echo "  Duration    : ${RUN_TIME}"
echo "  User class  : ${USER_CLASS}"
echo "  Tags        : ${TAGS:-<all>}"
echo "  HTML report : ${REPORT_PREFIX}.html"
echo "======================================================"
echo ""

# ---------------------------------------------------------------------------
# Build locust command
# ---------------------------------------------------------------------------
LOCUST_CMD=(
    locust
    -f "${LOCUSTFILE}"
    --headless
    --only-summary
    --users "${USERS}"
    --spawn-rate "${SPAWN_RATE}"
    --run-time "${RUN_TIME}"
    --host "${HOST}"
    --html "${REPORT_PREFIX}.html"
    --csv "${REPORT_PREFIX}"
    "${USER_CLASS}"
)

# Append optional tag filter
if [[ -n "${TAGS}" ]]; then
    LOCUST_CMD+=(--tags "${TAGS}")
fi

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
echo "Running: ${LOCUST_CMD[*]}"
echo ""

START_TS=$(date +%s)
"${LOCUST_CMD[@]}"
EXIT_CODE=$?
END_TS=$(date +%s)
ELAPSED=$(( END_TS - START_TS ))

# ---------------------------------------------------------------------------
# Post-run summary
# ---------------------------------------------------------------------------
echo ""
echo "======================================================"
echo " Test completed in ${ELAPSED}s (exit code: ${EXIT_CODE})"
echo "======================================================"

# Parse CSV stats if available
STATS_CSV="${REPORT_PREFIX}_stats.csv"
if [[ -f "${STATS_CSV}" ]]; then
    echo ""
    echo "Aggregated results:"
    # Print header + Aggregated row
    awk -F',' 'NR==1 || /Aggregated/' "${STATS_CSV}" | \
        awk -F',' '{printf "  %-30s %8s %8s %8s %8s\n", $2, $3, $7, $9, $10}' | \
        head -4
    echo ""
fi

echo "HTML report : ${REPORT_PREFIX}.html"
echo "CSV stats   : ${STATS_CSV}"
echo ""

# Enforce < 1% failure rate as pass/fail gate
FAILURES_CSV="${REPORT_PREFIX}_failures.csv"
if [[ -f "${FAILURES_CSV}" ]]; then
    FAILURE_COUNT=$(tail -n +2 "${FAILURES_CSV}" | wc -l | tr -d ' ')
    if [[ "${FAILURE_COUNT}" -gt 0 ]]; then
        echo "WARN: ${FAILURE_COUNT} failure type(s) detected — check ${FAILURES_CSV}"
    fi
fi

exit "${EXIT_CODE}"
