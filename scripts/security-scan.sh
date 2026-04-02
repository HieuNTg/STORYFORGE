#!/bin/bash
set -euo pipefail

# ── StoryForge Local Security Scan ──

PASS=0
FAIL=0

log()   { echo "[$(date '+%H:%M:%S')] $*"; }
ok()    { echo "  PASS  $*"; ((PASS++)); }
warn()  { echo "  WARN  $*"; ((FAIL++)); }

# ── 1. pip-audit: dependency vulnerability check ──
echo ""
log "Running pip-audit (dependency vulnerabilities)..."
if ! command -v pip-audit &> /dev/null; then
  log "pip-audit not found — installing..."
  pip install -q pip-audit
fi

if pip-audit --strict --desc 2>&1; then
  ok "pip-audit: no vulnerabilities found"
else
  warn "pip-audit: vulnerabilities detected (see above)"
fi

# ── 2. Known vulnerable package check ──
echo ""
log "Checking for known high-risk packages..."
RISKY_PKGS=("pyyaml<6" "pillow<10" "cryptography<41")
INSTALLED=$(pip list --format=freeze 2>/dev/null | tr '[:upper:]' '[:lower:]')

for pkg in "${RISKY_PKGS[@]}"; do
  name="${pkg%%[<>=]*}"
  if echo "$INSTALLED" | grep -q "^${name}=="; then
    version=$(echo "$INSTALLED" | grep "^${name}==" | cut -d= -f3)
    warn "Found potentially outdated: ${name}==${version} (check if ${pkg} applies)"
  else
    ok "Not installed or up-to-date: ${name}"
  fi
done

# ── 3. ruff security-related rules ──
echo ""
log "Running ruff (security rules: S, B)..."
if ruff check . --select S,B --ignore S101 --exclude vendor/ 2>&1; then
  ok "ruff: no security issues found"
else
  warn "ruff: security issues detected (see above)"
fi

# ── Summary ──
echo ""
echo "══════════════════════════════════════════"
echo "  Security Scan Summary"
echo "══════════════════════════════════════════"
echo "  Passed : ${PASS}"
echo "  Warned : ${FAIL}"
echo "  Time   : $(date '+%Y-%m-%d %H:%M:%S')"
echo "══════════════════════════════════════════"

if [[ $FAIL -gt 0 ]]; then
  echo "  Review warnings above before deploying."
  exit 1
fi
