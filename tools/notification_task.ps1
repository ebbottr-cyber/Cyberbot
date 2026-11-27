param(
    [ValidateSet('Status','Register','Start','Stop','Remove')][string]$Action = 'Status'
)
$ErrorActionPreference = 'Stop'
$name = 'Cyberbot-NotificationWorker'
$root = Split-Path $PSScriptRoot -Parent
$state = Join-Path $HOME '.cyberbot-private'
$python = Join-Path $state 'notification-venv\Scripts\python.exe'
$task = Get-ScheduledTask -TaskName $name -TaskPath '\' -ErrorAction SilentlyContinue
switch ($Action) {
    'Register' {
        if ($task) { throw 'Task already exists; no overwrite performed.' }
        if (-not (Test-Path $python)) { throw 'Run notification_setup.ps1 -Install first.' }
        $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        $exec = New-ScheduledTaskAction -Execute $python -Argument '-m tools.notification_runner --enable' -WorkingDirectory $root
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
        $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
        $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
        Register-ScheduledTask -TaskName $name -TaskPath '\' -Action $exec -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
    }
    'Start' { if (-not $task) { throw 'Task not registered.' }; Start-ScheduledTask -TaskName $name -TaskPath '\' }
    'Stop' { if ($task) { Stop-ScheduledTask -TaskName $name -TaskPath '\' } }
    'Remove' { if ($task) { if ($task.State -eq 'Running') { throw 'Stop task first.' }; Unregister-ScheduledTask -TaskName $name -TaskPath '\' -Confirm:$true } }
}
Get-ScheduledTask -TaskName $name -TaskPath '\' -ErrorAction SilentlyContinue | Select-Object TaskName,State
$health = Join-Path $state 'notification-health.json'
if (Test-Path $health) {
    Get-Content $health -Raw
    Write-Host ('Health file age seconds: ' + [math]::Round(((Get-Date).ToUniversalTime() - (Get-Item $health).LastWriteTimeUtc).TotalSeconds))
}
Write-Host 'Push delivery is not enabled by this task registration.'
