# Runs the full headline-detection monitor: scrape current Vegas lines,
# append a snapshot, then diff against the previous snapshot and flag any
# big movers. Meant to be the single entry point a scheduled task calls
# every few hours -- see data/README.md for Windows Task Scheduler setup.
#
# Logs every run to logs\vegas_monitor.log (created if missing) so you have
# a persistent record even though this runs unattended. Exits with the
# compare script's exit code (0 = quiet, 1 = big mover flagged) so the
# scheduled task's own "last run result" reflects whether something needs
# a look.

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $ProjectRoot "logs"
$LogFile = Join-Path $LogDir "vegas_monitor.log"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$Python = Join-Path $ProjectRoot "venv\Scripts\python.exe"
$Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

function Write-Log($text) {
    Add-Content -Path $LogFile -Value $text
}

Write-Log "===== $Timestamp ====="

Push-Location $ProjectRoot
try {
    $scrapeOutput = & $Python "scripts\scrape_vegas_snapshot.py" 2>&1 | Out-String
    Write-Log $scrapeOutput
    Write-Output $scrapeOutput

    $compareOutput = & $Python "scripts\compare_vegas_snapshots.py" 2>&1 | Out-String
    $compareExitCode = $LASTEXITCODE
    Write-Log $compareOutput
    Write-Output $compareOutput

    if ($compareExitCode -eq 1) {
        Write-Log "RESULT: BIG MOVER FLAGGED -- investigate."
    } else {
        Write-Log "RESULT: quiet, no action needed."
    }
}
finally {
    Pop-Location
}

exit $compareExitCode
