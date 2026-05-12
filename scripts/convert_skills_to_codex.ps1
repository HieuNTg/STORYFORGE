$ErrorActionPreference = "Stop"

$src = "C:\Users\Admin\OneDrive\Desktop\STORYFORGE\.claude\skills"
$dst = "C:\Users\Admin\.codex\skills"

# Skills to skip (not real skill dirs or already exist in .system)
$skipNames = @("common", "document-skills", "skill-creator")

$skills = Get-ChildItem -Path $src -Directory | Where-Object {
    $skipNames -notcontains $_.Name -and (Test-Path (Join-Path $_.FullName "SKILL.md"))
}

$converted = 0
$skipped = @()

foreach ($skill in $skills) {
    $skillName = $skill.Name
    $skillMd = Join-Path $skill.FullName "SKILL.md"

    $raw = Get-Content -Raw -LiteralPath $skillMd
    if ($raw -notmatch '(?s)^---\s*\r?\n(.*?)\r?\n---\s*\r?\n(.*)$') {
        $skipped += "$skillName (no frontmatter)"
        continue
    }
    $fm = $Matches[1]
    $body = $Matches[2]

    # Extract name + description
    $name = $null
    $desc = $null
    if ($fm -match '(?m)^name:\s*"?([^"\r\n]+)"?\s*$') { $name = $Matches[1].Trim() }
    if ($fm -match '(?ms)^description:\s*(.+?)(?=^\w+:|\Z)') {
        $desc = $Matches[1].Trim() -replace '\r?\n\s+', ' '
        $desc = $desc.Trim('"').Trim("'")
    }

    if (-not $name) { $name = $skillName }
    if (-not $desc) {
        $skipped += "$skillName (no description)"
        continue
    }

    # Build new SKILL.md with Codex-compatible frontmatter (name + description only)
    $descEscaped = $desc -replace '"', '\"'
    $newFm = @"
---
name: "$name"
description: "$descEscaped"
---
"@
    $newContent = "$newFm`r`n$body"

    # Copy whole skill dir then overwrite SKILL.md
    $targetDir = Join-Path $dst $skillName
    if (Test-Path $targetDir) {
        Remove-Item -Recurse -Force $targetDir
    }
    Copy-Item -Recurse -Path $skill.FullName -Destination $targetDir

    Set-Content -LiteralPath (Join-Path $targetDir "SKILL.md") -Value $newContent -NoNewline -Encoding UTF8

    $converted++
    Write-Host "OK  $skillName"
}

Write-Host ""
Write-Host "Converted: $converted"
if ($skipped.Count -gt 0) {
    Write-Host "Skipped:"
    $skipped | ForEach-Object { Write-Host "  - $_" }
}
