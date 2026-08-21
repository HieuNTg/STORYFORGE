# StoryForge local dev launcher
# Starts the FastAPI backend and Next.js frontend in two PowerShell windows.

param(
  [int]$FrontendPort = 3001
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Frontend = Join-Path $Root "frontend"
$BackendPort = 7860

if (-not (Test-Path (Join-Path $Root "app.py"))) {
  throw "Cannot find app.py. Run this script from the StoryForge repo root."
}

if (-not (Test-Path (Join-Path $Frontend "package.json"))) {
  throw "Cannot find frontend/package.json. Is the frontend folder missing?"
}

Write-Host "Starting StoryForge backend on http://localhost:$BackendPort ..." -ForegroundColor Cyan
Start-Process powershell -WorkingDirectory $Root -ArgumentList @(
  "-NoExit",
  "-ExecutionPolicy", "Bypass",
  "-Command",
  "$env:PYTHONNOUSERSITE='1'; python app.py"
)

# --- Node preflight -------------------------------------------------------
# A Node install can be present, correctly signed, and still be unable to run:
# a half-finished upgrade left `C:\Program Files\nodejs\node.exe` crashing with
# 0xC000001D (STATUS_ILLEGAL_INSTRUCTION) on this machine while a newer, working
# Node sat in the user's PATH behind it. Windows resolves the machine PATH
# before the user PATH, so the broken one won every lookup.
#
# That failure is nasty to diagnose from the symptoms: `npm` reports
# "Could not determine Node.js install directory", and Turbopack — which spawns
# its own child `node` for PostCSS — serves HTTP 500 on every page with the real
# cause buried in a panic log. So verify Node can actually EXECUTE (not just
# report --version, which the broken build still did) and, if not, fall back to
# another working install rather than failing in that confusing way.
function Test-NodeRuns([string]$exe) {
  try {
    & $exe -e "process.exit(0)" 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
  } catch { return $false }
}

$NodeDir = $null
$pathNode = (Get-Command node -ErrorAction SilentlyContinue).Source
if ($pathNode -and (Test-NodeRuns $pathNode)) {
  $NodeDir = Split-Path -Parent $pathNode
} else {
  if ($pathNode) {
    Write-Host "Node at '$pathNode' cannot execute scripts - looking for a working install..." -ForegroundColor Yellow
  }
  $candidates = @()
  $candidates += Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Filter "node-v*-win-x64" -Directory -Recurse -Depth 2 -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending | ForEach-Object { Join-Path $_.FullName "node.exe" }
  $candidates += "$env:ProgramFiles\nodejs\node.exe"
  foreach ($c in $candidates) {
    if ((Test-Path $c) -and (Test-NodeRuns $c)) { $NodeDir = Split-Path -Parent $c; break }
  }
  if (-not $NodeDir) {
    throw "No working Node.js found. Repair your install (e.g. 'winget uninstall --id OpenJS.NodeJS.22' as Administrator to drop a broken machine-scope copy), then re-run."
  }
  Write-Host "Using Node from: $NodeDir" -ForegroundColor Yellow
  Write-Host "  (fix the default install so child processes pick it up too)" -ForegroundColor Yellow
}

Write-Host "Starting StoryForge frontend on http://localhost:$FrontendPort ..." -ForegroundColor Cyan
# Prepend the chosen Node to PATH for the child shell. This must be a PATH edit,
# not just a direct exe call: Turbopack resolves `node` from PATH when it spawns
# its own workers, so calling a good node.exe directly is not enough on its own.
Start-Process powershell -WorkingDirectory $Frontend -ArgumentList @(
  "-NoExit",
  "-ExecutionPolicy", "Bypass",
  "-Command",
  "`$env:PATH='$NodeDir;' + `$env:PATH; npm run dev -- --port $FrontendPort"
)

Write-Host ""
Write-Host "StoryForge is starting." -ForegroundColor Green
Write-Host "Backend:  http://localhost:$BackendPort"
Write-Host "Frontend: http://localhost:$FrontendPort"
Write-Host "Open:     http://localhost:$FrontendPort/forge/"
