<#
.SYNOPSIS
    Blitz Culture -- register Windows Scheduled Tasks for orchestrator.py (Phase 5).

.DESCRIPTION
    Creates one daily-repeating task per posting slot (3-5x/day per the
    roadmap), each with a randomized delay so posts don't land at the exact
    same second every day. Every task calls orchestrator.py, which handles
    its own retry logic and failure logging (outputs/orchestrator_log.txt,
    outputs/orchestrator_failures.jsonl) -- this script layers Task
    Scheduler's own restart-on-failure on top of that.

    Re-run this script any time to update the schedule or switch modes --
    it registers with -Force, so existing tasks of the same name get
    overwritten rather than duplicated.

.PARAMETER Mode
    "Queue" (default) -- unattended, matches roadmap Phase 6: orchestrator
    runs with --queue, parking each post in outputs/pending_posts.json for
    you to review with review_pending.py. No post goes out without a human
    approving it.

    "Auto" -- fully autonomous (--auto): orchestrator publishes directly,
    no queue, no prompt. Only switch to this once Phase 6 testing looks
    clean -- see PHASE6_TESTING.md for the criteria.

.PARAMETER Times
    Local times (24h "HH:mm") to trigger a run each day. Default is 4 times
    (within the roadmap's 3-5/day range), spread across the day.

.PARAMETER RandomDelayMinutes
    Each trigger fires at its Times value plus a random delay up to this
    many minutes, so the account doesn't post at a suspiciously exact
    second every single day.

.EXAMPLE
    # First-time setup, Phase 6 mode (queue + human review)
    .\setup_scheduled_tasks.ps1

.EXAMPLE
    # After a clean week of Phase 6 testing, go fully autonomous
    .\setup_scheduled_tasks.ps1 -Mode Auto

.EXAMPLE
    # Custom cadence: 3 posts/day, wider random window
    .\setup_scheduled_tasks.ps1 -Times "10:00","15:00","20:00" -RandomDelayMinutes 60
#>
param(
    [ValidateSet("Queue", "Auto")]
    [string]$Mode = "Queue",

    [string[]]$Times = @("09:30", "13:00", "17:00", "20:30"),

    [int]$RandomDelayMinutes = 45,

    [string]$TaskNamePrefix = "BlitzCulture-Post"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$PythonExe   = Join-Path $ProjectRoot "venv\Scripts\python.exe"
$Orchestrator = Join-Path $ProjectRoot "orchestrator.py"

if (-not (Test-Path $PythonExe)) {
    throw "Couldn't find $PythonExe -- build the venv first (see README.md 'Build the two environments')."
}
if (-not (Test-Path $Orchestrator)) {
    throw "Couldn't find $Orchestrator -- run this script from the scheduling\ folder inside the project."
}

$modeArg = if ($Mode -eq "Auto") { "--auto" } else { "--queue" }
Write-Host "Registering $($Times.Count) daily task(s) in '$Mode' mode (orchestrator.py $modeArg)..." -ForegroundColor Cyan

$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "`"$Orchestrator`" $modeArg" `
    -WorkingDirectory $ProjectRoot

$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 10) `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20) `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries `
    -WakeToRun

# S4U logon: runs whether you're logged on or not, no stored password needed
# (unlike LogonType Password, which requires -User/-Password and re-prompts
# whenever your Windows password changes). Requires the account to have the
# "Log on as a batch job" right, which Register-ScheduledTask grants
# automatically for the account running this script.
$Principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType S4U `
    -RunLevel Limited

$registered = @()
foreach ($t in $Times) {
    $taskName = "$TaskNamePrefix-$($t -replace ':','')"
    $trigger = New-ScheduledTaskTrigger -Daily -At $t
    $trigger.RandomDelay = "PT$($RandomDelayMinutes)M"

    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $Action `
        -Trigger $trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Description "Blitz Culture posting pipeline ($Mode mode) -- runs orchestrator.py $modeArg. See PHASE6_TESTING.md." `
        -Force | Out-Null

    $registered += $taskName
    Write-Host "  [OK] $taskName -> daily at $t (+ up to ${RandomDelayMinutes}m random delay)"
}

Write-Host "`nDone. $($registered.Count) task(s) registered under Task Scheduler." -ForegroundColor Green
Write-Host "Logon type: S4U -- these now run whether you're logged on or not (no stored password)." -ForegroundColor Yellow
Write-Host "Your PC still has to be powered on (not asleep/hibernating) at trigger time." -ForegroundColor Yellow

if ($Mode -eq "Queue") {
    Write-Host "`nMode is 'Queue' -- nothing publishes automatically. Run review_pending.py periodically:" -ForegroundColor Cyan
    Write-Host "  $PythonExe review_pending.py"
} else {
    Write-Host "`nMode is 'Auto' -- posts will publish with NO human review. Make sure Phase 6 testing passed first." -ForegroundColor Red
}
