# Bounded local research launcher. Does not enable trading or download packages.
param(
    [Parameter(Mandatory=$true)][ValidateSet('Chronos','Backup')][string]$Mode
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
    if ($Mode -eq 'Chronos') {
        $os = Get-CimInstance -ClassName Win32_OperatingSystem
        if ([uint64]$os.FreePhysicalMemory -lt 4194304) {
            Write-Host 'WAIT_MEMORY'
            exit 75
        }
        $python = Join-Path $env:LOCALAPPDATA 'Cyberbot\ChronosRuntime\Scripts\python.exe'
        if (!(Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Chronos runtime missing.' }
        & $python (Join-Path $root 'tools\local_research\forward_learning_v2.py') $root 10
    } else {
        $python = Join-Path $root '.venv\Scripts\python.exe'
        if (!(Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Main Python runtime missing.' }
        & $python -m tools.local_research.forward_backup --root $root
    }
    exit $LASTEXITCODE
} finally {
    if ($owned) { $mutex.ReleaseMutex() }
    if ($null -ne $mutex) { $mutex.Dispose() }
    Pop-Location
}
