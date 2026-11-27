# Preview by default. Creates disabled tasks only; never starts or overwrites tasks.
param([switch]$Register)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$script = Join-Path $root 'scripts\ai-research-windows.ps1'
$plans = @(
    @{ Name = 'Cyberbot-AI-Chronos'; Mode = 'Chronos'; Time = '00:00'; Limit = 15 },
    @{ Name = 'Cyberbot-AI-ForwardBackup'; Mode = 'Backup'; Time = '03:15'; Limit = 5 }
)
if (-not $Register) {
    Write-Host 'PREVIEW: Chronos every 15 minutes; forward journal backup daily at 03:15 local time.'
    Write-Host 'Both tasks will be disabled, interactive user only, AC power only. No task started.'
    return
}
if (!(Test-Path -LiteralPath $script -PathType Leaf)) { throw 'Research launcher missing.' }
foreach ($plan in $plans) {
    if (Get-ScheduledTask -TaskName $plan.Name -ErrorAction SilentlyContinue) {
        throw ('Task already exists; no tasks registered: ' + $plan.Name)
    }
}
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$created = @()
try {
    foreach ($plan in $plans) {
        $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -NonInteractive -File "' + $script + '" -Mode ' + $plan.Mode) -WorkingDirectory $root
        if ($plan.Mode -eq 'Chronos') {
            $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddDays(1) -RepetitionInterval (New-TimeSpan -Minutes 15)
        } else {
            $trigger = New-ScheduledTaskTrigger -Daily -At '03:15'
        }
        $settings = New-ScheduledTaskSettingsSet -Disable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes $plan.Limit)
        Register-ScheduledTask -TaskName $plan.Name -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Opt-in local research only. No real orders or automatic model promotion.' | Out-Null
        $created += $plan.Name
    }
} catch {
    foreach ($name in $created) {
        Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    }
    throw
}
Write-Host 'Created disabled tasks. Verify runtimes, paths and data permissions before enabling.'
