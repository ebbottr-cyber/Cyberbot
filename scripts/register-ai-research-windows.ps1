# Preview by default. Creates disabled tasks only; never starts or overwrites tasks.
param([switch]$Register)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$script = Join-Path $root 'scripts\ai-research-windows.ps1'
$plans = @(
    @{ Name = 'Cyberbot-AI-Chronos'; Mode = 'Chronos'; Time = '00:01'; Interval = 15; Limit = 15 },
    @{ Name = 'Cyberbot-AI-RiverLive'; Mode = 'RiverLive'; Time = '00:00'; Interval = 15; Limit = 14 },
    @{ Name = 'Cyberbot-AI-LightGBM'; Mode = 'LightGBM'; Time = '02:12'; Interval = 0; Limit = 30 },
    @{ Name = 'Cyberbot-AI-RiverReplay'; Mode = 'RiverReplay'; Time = '00:13'; Interval = 30; Limit = 3 },
    @{ Name = 'Cyberbot-AI-ForwardBackup'; Mode = 'Backup'; Time = '03:15'; Interval = 0; Limit = 5 },
    @{ Name = 'Cyberbot-AI-Watchdog'; Mode = 'Watchdog'; Time = '00:05'; Interval = 5; Limit = 1 }
)
if (-not $Register) {
    Write-Host 'PREVIEW: Chronos every 15 minutes; River live every 15 minutes; LightGBM at 02:12; River replay every 30 minutes; forward backup at 03:15; read-only watchdog every 5 minutes, local time.'
    Write-Host 'All tasks will be disabled, interactive user only, AC power only. No task started.'
    return
}
if (!(Test-Path -LiteralPath $script -PathType Leaf)) { throw 'Research launcher missing.' }
$watchdog = Join-Path $root 'scripts\ai-watchdog-windows.ps1'
if (!(Test-Path -LiteralPath $watchdog -PathType Leaf)) { throw 'Research watchdog missing.' }
foreach ($plan in $plans) {
    if (Get-ScheduledTask -TaskPath '\' -TaskName $plan.Name -ErrorAction SilentlyContinue) {
        throw ('Task already exists; no tasks registered: ' + $plan.Name)
    }
}
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$created = @()
try {
    foreach ($plan in $plans) {
        $arguments = if ($plan.Mode -eq 'Watchdog') {
            '-NoProfile -NonInteractive -File "' + $watchdog + '" -CheckExitCode'
        } else {
            '-NoProfile -NonInteractive -File "' + $script + '" -Mode ' + $plan.Mode
        }
        $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments -WorkingDirectory $root
        $now = Get-Date
        $start = $now.Date.Add([TimeSpan]::Parse($plan.Time))
        if ($plan.Interval -gt 0) {
            while ($start -le $now) { $start = $start.AddMinutes($plan.Interval) }
            $trigger = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Minutes $plan.Interval)
        } else {
            if ($start -le $now) { $start = $start.AddDays(1) }
            $trigger = New-ScheduledTaskTrigger -Daily -At $start
        }
        $settings = New-ScheduledTaskSettingsSet -Disable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes $plan.Limit)
        Register-ScheduledTask -TaskPath '\' -TaskName $plan.Name -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Opt-in local research only. No real orders or automatic model promotion.' | Out-Null
        $created += $plan.Name
    }
} catch {
    foreach ($name in $created) {
        Unregister-ScheduledTask -TaskPath '\' -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    }
    throw
}
Write-Host 'Created disabled tasks. Verify runtimes, paths and data permissions before enabling.'
