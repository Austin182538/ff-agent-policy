<#
.SYNOPSIS
    Unregisters all Blitz Culture posting tasks created by setup_scheduled_tasks.ps1.
.EXAMPLE
    .\remove_scheduled_tasks.ps1
#>
param(
    [string]$TaskNamePrefix = "BlitzCulture-Post"
)

$tasks = Get-ScheduledTask -TaskName "$TaskNamePrefix-*" -ErrorAction SilentlyContinue
if (-not $tasks) {
    Write-Host "No tasks found matching '$TaskNamePrefix-*'."
    return
}

foreach ($t in $tasks) {
    Unregister-ScheduledTask -TaskName $t.TaskName -Confirm:$false
    Write-Host "Removed: $($t.TaskName)"
}
