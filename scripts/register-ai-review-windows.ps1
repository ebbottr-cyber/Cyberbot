# Opt-in coordinator task, separate from the existing six-task registrar.
# Preview by default. Creates one disabled task; never modifies existing tasks.
param([switch]$Register)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$name = 'Cyberbot-AI-ResearchReview'
$launcher = Join-Path $root 'scripts\ai-research-windows.ps1'
$runtime = Join-Path $env:LOCALAPPDATA 'Cyberbot\ReviewRuntime'
$python = Join-Path $runtime 'Scripts\python.exe'

if (!$Register) {
    Write-Host 'PREVIEW ONLY: ResearchReview daily at 02:45 local time, maximum 20 minutes.'
    Write-Host 'Disabled on registration; interactive user and AC power only. No missed-run catch-up.'
    Write-Host 'Existing tasks and configuration are preserved.'
    return
}
if (Get-ScheduledTask -TaskPath '\' -TaskName $name -ErrorAction SilentlyContinue) {
    throw 'ResearchReview task already exists; not overwritten.'
}
if (!(Test-Path -LiteralPath $launcher -PathType Leaf)) { throw 'Research launcher missing.' }
if (!(Test-Path -LiteralPath $python -PathType Leaf)) { throw 'ReviewRuntime missing; review setup first.' }
if (Test-Path -LiteralPath (Join-Path $runtime '.setup-incomplete')) { throw 'ReviewRuntime incomplete.' }
# Do not enable on creation or replay missed daily training outside maintenance.
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$arguments = '-NoProfile -NonInteractive -File "' + $launcher + '" -Mode ResearchReview'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments -WorkingDirectory $root
$now = Get-Date
$start = $now.Date.AddHours(2).AddMinutes(45)
if ($start -le $now) { $start = $start.AddDays(1) }
$trigger = New-ScheduledTaskTrigger -Daily -At $start
$settings = New-ScheduledTaskSettingsSet -Disable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
# -Force deliberately omitted. Existing task check is not a system-wide lock.
Register-ScheduledTask -TaskPath '\' -TaskName $name -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Optional local paired AI research. No model activation or real orders.' | Out-Null
Write-Host 'ResearchReview registered disabled. Verify runtime, resource admission and task settings before enabling.'
