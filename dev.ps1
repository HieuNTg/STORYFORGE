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
  "python app.py"
)

Write-Host "Starting StoryForge frontend on http://localhost:$FrontendPort ..." -ForegroundColor Cyan
Start-Process powershell -WorkingDirectory $Frontend -ArgumentList @(
  "-NoExit",
  "-ExecutionPolicy", "Bypass",
  "-Command",
  "npm run dev -- --port $FrontendPort"
)

Write-Host ""
Write-Host "StoryForge is starting." -ForegroundColor Green
Write-Host "Backend:  http://localhost:$BackendPort"
Write-Host "Frontend: http://localhost:$FrontendPort"
Write-Host "Open:     http://localhost:$FrontendPort/forge/"
