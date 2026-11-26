# Creates only a new, disabled, limited Cyberbot logon task. Never starts or overwrites one.
param([switch]$Register)
$ErrorActionPreference = 'Stop'
if (-not $Register) { Write-Host 'Preview only. Use -Register to create a disabled task.'; return }
$root = Split-Path -Parent $PSScriptRoot
$name = 'Cyberbot-Observed-Pilot'
if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) { throw 'Task already exists; not overwritten.' }
$script = Join-Path $root 'scripts\pilot-supervisor-windows.ps1'
if (-not (Test-Path -LiteralPath (Join-Path $root '.venv\Scripts\python.exe') -PathType Leaf)) { throw 'Run setup-windows.ps1 first.' }
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -NonInteractive -File "' + $script + '" -Continuous') -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -Disable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Cyberbot opt-in observed paper supervisor; no automatic entry or real orders.' | Out-Null
Write-Host 'Created disabled task. Verify local configuration before enabling. No task started.'
