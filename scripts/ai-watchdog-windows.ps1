# Read-only health audit of the five local research tasks. Never starts or enables tasks.
param([switch]$CheckExitCode)
$ErrorActionPreference = 'Stop'
$now = Get-Date
$plans = @(
    @{ Name='Cyberbot-AI-Chronos'; MaxAge=45; Limit=15 },
    @{ Name='Cyberbot-AI-RiverLive'; MaxAge=45; Limit=14 },
    @{ Name='Cyberbot-AI-RiverReplay'; MaxAge=90; Limit=3 },
    @{ Name='Cyberbot-AI-LightGBM'; MaxAge=1500; Limit=30 },
    @{ Name='Cyberbot-AI-ForwardBackup'; MaxAge=1500; Limit=5 }
)
$rows = @()
foreach ($plan in $plans) {
    # Enumerate exact root-task names only. Do not touch unrelated jobs.
    $task = Get-ScheduledTask -TaskPath '\' -TaskName $plan.Name -ErrorAction SilentlyContinue
    if ($null -eq $task) {
        $rows += [ordered]@{ name=$plan.Name; status='NOT_REGISTERED' }
        continue
    }
    $info = Get-ScheduledTaskInfo -InputObject $task
    $last = $info.LastRunTime
    $age = if ($last.Year -ge 2000) { ($now-$last).TotalMinutes } else { $null }
    $code = [long]$info.LastTaskResult
    $state = [string]$task.State
    $status = 'REVIEW_REQUIRED'
    if ($state -eq 'Disabled') { $status = 'DISABLED' }
    elseif ($null -ne $age -and $age -lt -1) { $status = 'CLOCK_REVIEW_REQUIRED' }
    elseif ($state -eq 'Running') {
        if ($null -ne $age -and $age -gt ($plan.Limit+2)) { $status='OVERRUN_REVIEW_REQUIRED' }
        else { $status='RUNNING' }
    }
    elseif ($null -eq $age -or $code -eq 267011) { $status='NOT_RUN' }
    elseif ($code -eq 75) {
        if ($age -gt $plan.MaxAge) { $status='STALE_DEFERRED' }
        else { $status='DEFERRED' }
    }
    elseif ($code -eq 0) {
        if ($age -gt $plan.MaxAge) { $status='STALE' }
        else { $status='EXIT_OK' }
    }
    else { $status='FAILED' }
    $rows += [ordered]@{
        name=$plan.Name; status=$status; state=$state; last_result=$code
        last_run_utc=$(if ($null -ne $age) { $last.ToUniversalTime().ToString('o') } else { $null })
        next_run_utc=$(if ($info.NextRunTime.Year -ge 2000) { $info.NextRunTime.ToUniversalTime().ToString('o') } else { $null })
        missed_runs=$info.NumberOfMissedRuns
    }
}
$problem = @($rows | Where-Object { $_.status -in @('FAILED','STALE','STALE_DEFERRED','REVIEW_REQUIRED','OVERRUN_REVIEW_REQUIRED','CLOCK_REVIEW_REQUIRED') }).Count
$waiting = @($rows | Where-Object { $_.status -in @('DEFERRED','NOT_RUN','NOT_REGISTERED','DISABLED') }).Count
$result = [ordered]@{
    checked_at_utc=$now.ToUniversalTime().ToString('o')
    status=$(if ($problem -gt 0) { 'REVIEW_REQUIRED' } elseif ($waiting -gt 0) { 'NOT_FULLY_RUNNING' } else { 'SCHEDULER_OK' })
    tasks=$rows
    model_quality_verified=$false
    automatic_restart=$false
    task_configuration_modified=$false
    real_orders=$false
}
$result | ConvertTo-Json -Depth 5
if ($CheckExitCode) {
    if ($problem -gt 0) { exit 2 }
    if ($waiting -gt 0) { exit 75 }
    exit 0
}
