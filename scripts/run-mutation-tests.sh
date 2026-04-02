#!/usr/bin/env bash
# scripts/run-mutation-tests.sh
# Run mutation tests against StoryForge's critical modules and fail if
# mutation score drops below the 60% threshold.
#
# Usage:
#   bash scripts/run-mutation-tests.sh
#
# Requirements:
#   pip install mutmut
#
# Output:
#   html/index.html  — HTML mutation report
#   exits 1          — if mutation score < 60%

set -euo pipefail

THRESHOLD=60

TARGET_PATHS="services/auth.py,services/token_cost_tracker.py,middleware/rbac.py,pipeline/agents/debate_orchestrator.py"

echo "==> Running mutmut on targeted modules..."
mutmut run \
  --paths-to-mutate "$TARGET_PATHS" \
  --tests-dir tests \
  --no-progress || true   # mutmut exits non-zero when mutants survive — handle below

echo ""
echo "==> Generating HTML report..."
mutmut html

echo ""
echo "==> Mutation results summary:"
mutmut results

# Parse killed vs total mutants from mutmut's result output
KILLED=$(mutmut results 2>/dev/null | grep -E "^[0-9]+ mutants were killed" | grep -oE "^[0-9]+" || echo "0")
TOTAL=$(mutmut results 2>/dev/null | grep -E "^[0-9]+ mutants" | grep -oE "^[0-9]+" | head -1 || echo "1")

if [ "$TOTAL" -eq 0 ]; then
  echo "WARNING: No mutants generated — check that target files exist."
  exit 1
fi

SCORE=$(( KILLED * 100 / TOTAL ))
echo ""
echo "Mutation score: ${SCORE}% (${KILLED}/${TOTAL} killed) — threshold: ${THRESHOLD}%"

if [ "$SCORE" -lt "$THRESHOLD" ]; then
  echo "FAIL: Mutation score ${SCORE}% is below the required ${THRESHOLD}%."
  echo "      Open html/index.html to review surviving mutants."
  exit 1
else
  echo "PASS: Mutation score ${SCORE}% meets threshold."
fi
