# Full-suite gate runner: runs the test suite in separate processes to avoid
# native-state accumulation crashes (0xC0000409/0xC0000005 observed on
# single-process full-suite runs on Windows — lazy torch loads in worker
# threads). Coverage is combined via --cov-append + final `coverage report`.
# Usage: pwsh scripts/run_gate_chunks.ps1   (run from repo root)
$ErrorActionPreference = "Continue"
$out = "gate_chunks_output.txt"
"" | Out-File $out

$files = Get-ChildItem tests -Filter "test_*.py" -File | Sort-Object Name | ForEach-Object { "tests/$($_.Name)" }
$n = [math]::Ceiling($files.Count / 3)
$g1 = $files[0..($n - 1)]
$g2 = $files[$n..(2 * $n - 1)]
$g3 = $files[(2 * $n)..($files.Count - 1)]

$cov = @("--cov=pipeline", "--cov=services", "--cov=api", "--cov=middleware", "--cov-report=", "--cov-fail-under=0")

"=== CHUNK1 ($($g1.Count) files) ===" | Out-File -Append $out
python -m pytest @g1 -q -m "not calibration and not bench" @cov --tb=short 2>&1 | Out-File -Append $out
"EXIT1=$LASTEXITCODE" | Out-File -Append $out

"=== CHUNK2 ($($g2.Count) files) ===" | Out-File -Append $out
python -m pytest @g2 -q -m "not calibration and not bench" @cov --cov-append --tb=short 2>&1 | Out-File -Append $out
"EXIT2=$LASTEXITCODE" | Out-File -Append $out

"=== CHUNK3 ($($g3.Count) files) ===" | Out-File -Append $out
python -m pytest @g3 -q -m "not calibration and not bench" @cov --cov-append --tb=short 2>&1 | Out-File -Append $out
"EXIT3=$LASTEXITCODE" | Out-File -Append $out

$dirs = @("tests/benchmarks", "tests/golden", "tests/load", "tests/performance", "tests/security") | Where-Object { Test-Path $_ }
"=== CHUNK4 (subdirs: $($dirs -join ', ')) ===" | Out-File -Append $out
python -m pytest @dirs -q -m "not calibration and not bench" @cov --cov-append --tb=short 2>&1 | Out-File -Append $out
"EXIT4=$LASTEXITCODE" | Out-File -Append $out

"=== CHUNK5 (tests/perf, fresh process, real model) ===" | Out-File -Append $out
python -m pytest tests/perf -q --no-cov --tb=short 2>&1 | Select-Object -Last 3 | Out-File -Append $out
"EXIT5=$LASTEXITCODE" | Out-File -Append $out

"=== COMBINED COVERAGE ===" | Out-File -Append $out
python -m coverage report 2>&1 | Select-Object -Last 5 | Out-File -Append $out
"DONE" | Out-File -Append $out
