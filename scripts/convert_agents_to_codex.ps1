$ErrorActionPreference = "Stop"

$globalSrc  = "C:\Users\Admin\.claude\agents"
$projectSrc = "C:\Users\Admin\OneDrive\Desktop\STORYFORGE\.claude\agents"
$dst        = "C:\Users\Admin\.codex\skills\agency"
$specDir    = Join-Path $dst "specialists"

if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
New-Item -ItemType Directory -Force -Path $specDir | Out-Null

$index = [System.Collections.Generic.List[object]]::new()

function Convert-Agent {
    param([string]$file, [string]$origin)

    $raw = Get-Content -Raw -LiteralPath $file
    if ($raw -notmatch '(?s)^---\s*\r?\n(.*?)\r?\n---\s*\r?\n(.*)$') { return $null }
    $fm = $Matches[1]; $body = $Matches[2]

    $name = $null; $desc = $null
    if ($fm -match '(?m)^name:\s*"?([^"\r\n]+)"?\s*$') { $name = $Matches[1].Trim() }
    if ($fm -match '(?ms)^description:\s*(.+?)(?=^\w+:|\Z)') {
        $desc = ($Matches[1].Trim() -replace '\r?\n\s+', ' ').Trim('"').Trim("'")
    }
    if (-not $name -or -not $desc) { return $null }

    # Slug from file basename (preserves user's original taxonomy)
    $slug = [System.IO.Path]::GetFileNameWithoutExtension($file)
    if ($origin -eq "project") { $slug = "storyforge-$slug" }

    return @{
        slug = $slug
        name = $name
        description = $desc
        body = $body
        origin = $origin
    }
}

$converted = 0; $skipped = 0
$seen = @{}

# Project agents first (priority — they take precedence if naming clash)
foreach ($f in Get-ChildItem -Path $projectSrc -Filter "*.md" -File) {
    $a = Convert-Agent -file $f.FullName -origin "project"
    if ($null -eq $a) { $skipped++; continue }
    if ($seen.ContainsKey($a.slug)) { continue }
    $seen[$a.slug] = $true

    $out = @"
---
name: "$($a.name)"
description: "$($a.description -replace '"', '\"')"
origin: "storyforge-project"
---

$($a.body)
"@
    Set-Content -LiteralPath (Join-Path $specDir "$($a.slug).md") -Value $out -NoNewline -Encoding UTF8
    $index.Add($a)
    $converted++
}

# Global agents
foreach ($f in Get-ChildItem -Path $globalSrc -Filter "*.md" -File) {
    $a = Convert-Agent -file $f.FullName -origin "global"
    if ($null -eq $a) { $skipped++; continue }
    if ($seen.ContainsKey($a.slug)) { continue }
    $seen[$a.slug] = $true

    $out = @"
---
name: "$($a.name)"
description: "$($a.description -replace '"', '\"')"
origin: "global"
---

$($a.body)
"@
    Set-Content -LiteralPath (Join-Path $specDir "$($a.slug).md") -Value $out -NoNewline -Encoding UTF8
    $index.Add($a)
    $converted++
}

# Build INDEX.md (one line per specialist for fast scanning)
$indexLines = @("# Specialist Index", "", "Each entry: `slug` — name — description.", "Load via `specialists/<slug>.md` when relevant.", "")
foreach ($a in ($index | Sort-Object slug)) {
    $line = "- ``$($a.slug)`` — **$($a.name)** — $($a.description)"
    $indexLines += $line
}
Set-Content -LiteralPath (Join-Path $dst "INDEX.md") -Value ($indexLines -join "`r`n") -Encoding UTF8

# Build SKILL.md (the entry point Codex auto-discovers)
$skillMd = @'
---
name: "agency"
description: "Deploy domain-specialist personas (200+ experts) for tasks needing deep expertise — code review, security audit, architecture design, UX, marketing, legal, finance, regional/cultural strategy (China, Korea, France), game dev (Unity/Unreal/Godot), AI/ML, sales, ops, and more. Use when the user requests a specific expert role, when a task clearly benefits from a specialist perspective, or when the user invokes `/agency`. Browse `INDEX.md` to find the right specialist, then load that specialist's persona from `specialists/<slug>.md` and adopt their voice, framing, and method for the response."
---

# Agency Skill

A library of 200+ specialist personas converted from Claude Code subagents. Each specialist is a self-contained markdown persona file with a strict role, voice, and methodology.

## How to use

1. **Find the specialist**: Read `INDEX.md` and pick the slug whose description matches the task.
2. **Load the persona**: Read `specialists/<slug>.md` for full instructions, identity, mission, and constraints.
3. **Adopt the role**: Respond *as* that specialist — match their voice, frameworks, and quality bar. Do not break character to over-explain that you are role-playing.
4. **Combine when needed**: Multi-domain tasks may load 2-3 specialists. Cite which you're channeling for clarity.

## When NOT to use

- Trivial tasks (greetings, single-line edits, basic commands).
- When the user is mid-conversation with general assistance — don't suddenly shift into a persona unless asked.
- When no specialist clearly matches — better to answer plainly than force a bad fit.

## Origin tags

- `storyforge-project` — agents specific to the StoryForge codebase (writer, debugger, planner, etc.).
- `global` — general-purpose specialists from the user's global Claude agent library.

Project specialists take precedence on naming collisions.
'@

Set-Content -LiteralPath (Join-Path $dst "SKILL.md") -Value $skillMd -NoNewline -Encoding UTF8

Write-Host "Converted: $converted"
Write-Host "Skipped (no frontmatter): $skipped"
Write-Host "Output: $dst"
