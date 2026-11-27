# Read-only task audit; optional bounded local health history. Never starts or enables tasks.
param([switch]$CheckExitCode,[switch]$Persist)
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
$resources = $null
try {
    $os = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop
    $root = Split-Path -Parent $PSScriptRoot
    $disk = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($root))
    if ($null -ne $os.FreePhysicalMemory -and $null -ne $os.TotalVisibleMemorySize) {
        $resources = [ordered]@{
            free_ram_bytes = ([long]$os.FreePhysicalMemory * 1024)
            total_ram_bytes = ([long]$os.TotalVisibleMemorySize * 1024)
            free_disk_bytes = [long]$disk.AvailableFreeSpace
            total_disk_bytes = [long]$disk.TotalSize
            scope = 'host_sample_not_process_usage'
        }
    }
} catch { $resources = $null }
$result = [ordered]@{
    resources=$resources
    checked_at_utc=$now.ToUniversalTime().ToString('o')
    status=$(if ($problem -gt 0) { 'REVIEW_REQUIRED' } elseif ($waiting -gt 0) { 'NOT_FULLY_RUNNING' } else { 'SCHEDULER_OK' })
    tasks=$rows
    model_quality_verified=$false
    automatic_restart=$false
    task_configuration_modified=$false
    real_orders=$false
}
if ($Persist) {
    $root = Split-Path -Parent $PSScriptRoot
    $var = Get-Item -LiteralPath (Join-Path $root 'var') -ErrorAction Stop
    if (!$var.PSIsContainer -or ($var.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Unsafe local var directory.'
    }
    $folder = Join-Path $var.FullName 'ai-health'
    if (!(Test-Path -LiteralPath $folder)) {
        New-Item -ItemType Directory -Path $folder -ErrorAction Stop | Out-Null
    }
    $item = Get-Item -LiteralPath $folder
    if (!$item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Unsafe health directory.'
    }
    $disk = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($folder))
    if ($disk.AvailableFreeSpace -lt 5GB) {
        Write-Warning 'Health history not written: insufficient disk reserve.'
    } else {
        $path = Join-Path $folder 'watchdog-history.json'
        $mutex = [Threading.Mutex]::new($false, ('Local\CyberbotAIHealth-' + [Security.Principal.WindowsIdentity]::GetCurrent().User.Value))
        $owned = $false
        $tmp = $null
        try {
            try { $owned = $mutex.WaitOne(0) }
            catch [Threading.AbandonedMutexException] { $owned = $true }
            if (!$owned) { throw 'Health history writer busy.' }
            $history = @()
            if (Test-Path -LiteralPath $path) {
                $existing = Get-Item -LiteralPath $path
                if ($existing.PSIsContainer -or ($existing.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $existing.Length -gt 2MB) {
                    throw 'Unsafe or oversized health history.'
                }
                $history = @(Get-Content -LiteralPath $path -Raw | ConvertFrom-Json -ErrorAction Stop)
            }
            # Bounded diagnostics only, no market data or raw stderr.
            $history = @(@($history) + @($result) | Select-Object -Last 288)
            $json = ConvertTo-Json -InputObject $history -Depth 7 -Compress
            $tmp = Join-Path $folder ('.watchdog-' + [Guid]::NewGuid().ToString('N') + '.tmp')
            [IO.File]::WriteAllText($tmp,$json,[Text.UTF8Encoding]::new($false))
            if (Test-Path -LiteralPath $path) {
                [IO.File]::Replace($tmp,$path,$null)
            } else {
                [IO.File]::Move($tmp,$path)
            }
        } finally {
            if ($null -ne $tmp -and (Test-Path -LiteralPath $tmp)) { Remove-Item -LiteralPath $tmp }
            if ($owned) { $mutex.ReleaseMutex() }
            $mutex.Dispose()
        }
    }
}
$result | ConvertTo-Json -Depth 5
if ($CheckExitCode) {
    if ($problem -gt 0) { exit 2 }
    if ($waiting -gt 0) { exit 75 }
    exit 0
}
