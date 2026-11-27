# Bounded local research launcher. Does not enable trading or download packages.
param(
    [Parameter(Mandatory=$true)][ValidateSet('Chronos','LightGBM','RiverReplay','Backup')][string]$Mode
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
$mutex = $null
$owned = $false
try {
    if ($env:CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED -ne '1') {
        Write-Host 'WAIT_RIGHTS'
        exit 75
    }
    $folder = Join-Path $root 'var\ai'
    if (!(Test-Path -LiteralPath $folder -PathType Container)) {
        throw 'Local research folder missing.'
    }
    $disk = [System.IO.DriveInfo]::new([System.IO.Path]::GetPathRoot($folder))
    if ($disk.AvailableFreeSpace -lt 5GB) { Write-Host 'WAIT_DISK'; exit 75 }
    # A per-user named mutex coordinates the scheduled research jobs.
    $sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $mutex = [System.Threading.Mutex]::new($false, ('Local\CyberbotAI-' + $sid))
    try { $owned = $mutex.WaitOne(0) }
    catch [System.Threading.AbandonedMutexException] { $owned = $true }
    if (!$owned) { Write-Host 'WAIT_AI_JOB'; exit 75 }
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $env:HF_HUB_OFFLINE = '1'
    $env:TRANSFORMERS_OFFLINE = '1'
    $env:HF_HUB_DISABLE_TELEMETRY = '1'
    $env:CUDA_VISIBLE_DEVICES = ''
    $env:OMP_NUM_THREADS = '2'
    $env:MKL_NUM_THREADS = '2'
    $env:OPENBLAS_NUM_THREADS = '2'
    $minimumFreeKiB = @{ Chronos = 4194304; LightGBM = 5242880; RiverReplay = 3145728; Backup = 0 }
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
        'Backup' {
            $python = Join-Path $root '.venv\Scripts\python.exe'
            $arguments = @('-m','tools.local_research.forward_backup','--root',$root)
        }
    }
    if (!(Test-Path -LiteralPath $python -PathType Leaf)) { throw ('Research runtime missing: ' + $Mode) }
    & $python @arguments
    exit $LASTEXITCODE
} finally {
    if ($owned) { $mutex.ReleaseMutex() }
    if ($null -ne $mutex) { $mutex.Dispose() }
    Pop-Location
}
