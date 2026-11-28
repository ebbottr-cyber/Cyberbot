# Local research only. No task registration unless explicitly requested.
param(
    [ValidateSet('Once','Continuous','Status','Register','Start','Stop')][string]$Mode='Status',
    [ValidateRange(900,86400)][int]$Interval=3600
)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$python=Join-Path $root 'var\fund-etf-venv\Scripts\python.exe'
$name='Cyberbot-Fund-ETF-Worker'
$script=Join-Path $root 'scripts\fund-etf-windows.ps1'
if (-not (Test-Path $python)) { throw 'Run setup-fund-etf-windows.ps1 first.' }
Push-Location $root
try {
    switch ($Mode) {
        'Register' {
            if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) { throw 'Task exists; not overwritten.' }
            $user=[System.Security.Principal.WindowsIdentity]::GetCurrent().Name
            $arguments='-NoProfile -File "'+$script+'" -Mode Continuous -Interval '+$Interval
            $action=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments -WorkingDirectory $root
            $trigger=New-ScheduledTaskTrigger -AtLogOn -User $user
            $principal=New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
            $settings=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -Disable
            Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
            Write-Host 'Registered disabled. Review config before explicitly enabling.'
        }
        'Start' {
            if (-not (Test-Path (Join-Path $root 'var\fund-etf-config.json'))) { throw 'Missing research configuration.' }
            $task=Get-ScheduledTask -TaskName $name
            if ($task.Actions.Count -ne 1 -or $task.Actions[0].Arguments -notlike ('*"'+$script+'"*')) { throw 'Existing task belongs to another checkout.' }
            Enable-ScheduledTask -TaskName $name | Out-Null
            Start-ScheduledTask -TaskName $name
        }
        'Stop' {
            $task=Get-ScheduledTask -TaskName $name
            if ($task.Actions.Count -ne 1 -or $task.Actions[0].Arguments -notlike ('*"'+$script+'"*')) { throw 'Existing task belongs to another checkout.' }
            Disable-ScheduledTask -TaskName $name | Out-Null
            Stop-ScheduledTask -TaskName $name
        }
        'Status' {
            Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue | Select-Object TaskName,State
            & $python -m tools.fund_etf_worker --status
        }
        default {
            if (-not (Test-Path (Join-Path $root 'var\fund-etf-config.json'))) { throw 'Missing research configuration.' }
            $argsWorker=@('-m','tools.fund_etf_worker','--interval',"$Interval")
            if ($Mode -eq 'Continuous') { $argsWorker+='--loop' }
            & $python @argsWorker
            if ($LASTEXITCODE -ne 0) { throw "Fund ETF worker exited: $LASTEXITCODE" }
        }
    }
} finally { Pop-Location }
