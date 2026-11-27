# Bounded local research launcher. Does not enable trading or download packages.
param(
    [Parameter(Mandatory=$true)][ValidateSet('Chronos','LightGBM','RiverReplay','RiverLive','Backup')][string]$Mode
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
$locks = @()
$held = @()
try {
    if ($env:CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED -ne '1') {
        Write-Host 'WAIT_RIGHTS'
        exit 75
    }
    # Leave a daily maintenance window for batch training and backup.
    # Local wall clock, matching the Windows task triggers. Existing tasks
    # are not stopped; mutex admission still protects against overruns.
    $minuteOfDay = (Get-Date).TimeOfDay.TotalMinutes
    if ($Mode -in @('Chronos','RiverLive','RiverReplay') -and
        $minuteOfDay -ge 120 -and $minuteOfDay -lt 220) {
        Write-Host 'WAIT_MAINTENANCE_WINDOW'
        exit 75
    }
    $folder = Join-Path $root 'var\ai'
    if (!(Test-Path -LiteralPath $folder -PathType Container)) {
        throw 'Local research folder missing.'
    }
    $disk = [System.IO.DriveInfo]::new([System.IO.Path]::GetPathRoot($folder))
    if ($disk.AvailableFreeSpace -lt 5GB) { Write-Host 'WAIT_DISK'; exit 75 }
    # Chronos and prospective River must overlap. All other scheduled modes
    # require both locks. Nonblocking admission avoids a lock-order deadlock.
    $sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $names = if ($Mode -eq 'Chronos') { @('Heavy') }
             elseif ($Mode -eq 'RiverLive') { @('Live') }
             else { @('Heavy','Live') }
    foreach ($name in $names) {
        $lock = [System.Threading.Mutex]::new($false, ('Local\CyberbotAI-' + $sid + '-' + $name))
        $locks += $lock
        try { $owned = $lock.WaitOne(0) }
        catch [System.Threading.AbandonedMutexException] { $owned = $true }
        if (!$owned) { Write-Host 'WAIT_AI_JOB'; exit 75 }
        $held += $lock
    }
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $env:HF_HUB_OFFLINE = '1'
    $env:TRANSFORMERS_OFFLINE = '1'
    $env:HF_HUB_DISABLE_TELEMETRY = '1'
    $env:CUDA_VISIBLE_DEVICES = ''
    $env:OMP_NUM_THREADS = '2'
    $env:MKL_NUM_THREADS = '2'
    $env:OPENBLAS_NUM_THREADS = '2'
    $minimumFreeKiB = @{ Chronos = 4194304; LightGBM = 5242880; RiverReplay = 3145728; RiverLive = 3145728; Backup = 0 }
    if ($minimumFreeKiB[$Mode] -gt 0) {
        $os = Get-CimInstance -ClassName Win32_OperatingSystem
        if ($null -eq $os.FreePhysicalMemory -or [uint64]$os.FreePhysicalMemory -lt $minimumFreeKiB[$Mode]) {
            Write-Host 'WAIT_MEMORY'
            exit 75
        }
    }
    $runtime = Join-Path $env:LOCALAPPDATA 'Cyberbot'
    switch ($Mode) {
        'Chronos' {
            $python = Join-Path $runtime 'ChronosRuntime\Scripts\python.exe'
            $arguments = @((Join-Path $root 'tools\local_research\forward_learning_v2.py'), $root, '10')
        }
        'LightGBM' {
            $python = Join-Path $runtime 'LightGBMRuntime\Scripts\python.exe'
            $arguments = @('-m','tools.local_research.lightgbm_journal','--root',$root)
        }
        'RiverReplay' {
            $python = Join-Path $runtime 'RiverRuntime\Scripts\python.exe'
            $arguments = @('-m','tools.local_research.river_journal','--root',$root)
        }
        'RiverLive' {
            if (!(Test-Path -LiteralPath (Join-Path $folder 'forward-models-v2.sqlite3') -PathType Leaf)) {
                Write-Host 'WAIT_SOURCE'
                exit 75
            }
            $python = Join-Path $runtime 'RiverRuntime\Scripts\python.exe'
            $arguments = @('-m','tools.local_research.river_live_shadow','--root',$root,'--seconds','720')
            $env:OMP_NUM_THREADS = '1'
            $env:MKL_NUM_THREADS = '1'
            $env:OPENBLAS_NUM_THREADS = '1'
        }
        'Backup' {
            $python = Join-Path $root '.venv\Scripts\python.exe'
            $arguments = @('-m','tools.local_research.forward_backup','--root',$root)
        }
    }
    if (!(Test-Path -LiteralPath $python -PathType Leaf)) { throw ('Research runtime missing: ' + $Mode) }
    $runtimeRoot = Split-Path -Parent (Split-Path -Parent $python)
    if (Test-Path -LiteralPath (Join-Path $runtimeRoot '.setup-incomplete')) {
        throw ('Incomplete research runtime: ' + $Mode)
    }
    & $python @arguments
    exit $LASTEXITCODE
} finally {
    foreach ($lock in $held) { $lock.ReleaseMutex() }
    foreach ($lock in $locks) { $lock.Dispose() }
    Pop-Location
}
