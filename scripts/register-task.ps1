#requires -Version 5.1
<#
.SYNOPSIS
    Register a Windows Scheduled Task that runs mvp-tick every 15 minutes.

.DESCRIPTION
    Idempotent: if the task already exists it is replaced. Wakes the machine
    from sleep if needed (WakeToRun), retries when the trigger window is
    missed (StartWhenAvailable), skips a new instance if the previous one is
    still running (MultipleInstances IgnoreNew). Logs to
    $env:USERPROFILE\trumporacle-tick.log.

.NOTES
    Re-run anytime to refresh the task definition.
    Source kept ASCII-only so Windows PowerShell 5.1 (cp1252) reads it
    correctly; the project path with accents is resolved at runtime via
    PSScriptRoot, which the OS returns natively as UTF-16.
#>

$ErrorActionPreference = 'Stop'

$TaskName = 'Trumporacle-Tick'
$BashExe  = 'C:\Users\camauger\AppData\Local\Programs\Git\bin\bash.exe'

# Resolve tick.sh next to this script. Convert backslashes to forward slashes
# so the path is acceptable to bash.exe (MSYS) when passed as -l argument.
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Definition
$TickShWin   = Join-Path $ScriptDir 'tick.sh'
if (-not (Test-Path $TickShWin)) {
    throw "tick.sh not found at $TickShWin"
}
$TickShBash  = ($TickShWin -replace '\\', '/')

# Quote the bash arg in double quotes so bash sees the path as a single token.
$BashArgs    = '-l "' + $TickShBash + '"'
$LogPath     = Join-Path $env:USERPROFILE 'trumporacle-tick.log'

if (-not (Test-Path $BashExe)) {
    throw "bash.exe not found at $BashExe"
}

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed existing task $TaskName."
}

$action  = New-ScheduledTaskAction -Execute $BashExe -Argument $BashArgs
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 15)

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 12) `
    -MultipleInstances IgnoreNew `
    -WakeToRun

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description 'TRUMPORACLE: ingest + predict + outcomes (15 min cycle)'

Write-Host ''
Write-Host "Task '$TaskName' registered." -ForegroundColor Green
Write-Host "Logs:        $LogPath"
Write-Host "Manual run:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Status:      Get-ScheduledTaskInfo -TaskName '$TaskName'"
Write-Host "Disable:     Disable-ScheduledTask -TaskName '$TaskName'"
Write-Host "Remove:      Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
