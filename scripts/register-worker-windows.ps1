# Optional registration, explicitly invoked by the PC operator.
param([switch]$Register)
$ErrorActionPreference = 'Stop'
if (-not $Register) { Write-Host 'Use -Register to create the Cyberbot-only logon task.'; return }
$root = Split-Path -Parent $PSScriptRoot
$name = 'Cyberbot-Research-Worker'
if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) { throw 'Task already exists; not overwritten.' }
$script = Join-Path $root 'scripts\worker-windows.ps1'
if (-not (Test-Path (Join-Path $root '.venv\Scripts\python.exe'))) { throw 'Run setup-windows.ps1 first.' }
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -File "' + $script + '"') -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Cyberbot local offline synthetic research; no orders or price downloads.' | Out-Null
Write-Host "Registered $name. Start explicitly or at next sign-in."
