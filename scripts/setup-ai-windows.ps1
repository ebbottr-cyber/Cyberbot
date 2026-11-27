# Preview by default. Installs only new isolated LightGBM/River environments.
# Existing runtimes, model weights, databases, tasks and main venv are not modified.
param([switch]$Install,[switch]$IncludeReviewRuntime)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$base = Join-Path $env:LOCALAPPDATA 'Cyberbot'
$plans = @(
    @{ Name='LightGBMRuntime'; Package='lightgbm==4.6.0'; Module='lightgbm'; Version='4.6.0' },
    @{ Name='RiverRuntime'; Package='river==0.23.0'; Module='river'; Version='0.23.0' }
)
if ($IncludeReviewRuntime) {
    $plans += @{ Name='ReviewRuntime'; Package=@('lightgbm==4.6.0','river==0.23.0'); Module=@('lightgbm','river'); Version=@('4.6.0','0.23.0') }
}
if (!$Install) {
    Write-Host 'PREVIEW ONLY. Existing Chronos CPU runtime is preserved.'
    foreach ($plan in $plans) {
        $target = Join-Path $base $plan.Name
        Write-Host (($plan.Package -join ', ') + ' -> ' + $target + ' ; exists=' + (Test-Path -LiteralPath $target))
    }
    Write-Host 'Use -Install only after reviewing package sources. No tasks registered or enabled.'
    return
}
if (!(Test-Path -LiteralPath (Join-Path $root 'tools\local_research\river_review.py') -PathType Leaf)) {
    throw 'Reviewed Cyberbot research checkout required.'
}
$python = Join-Path $root '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Existing Cyberbot Python required.' }
& $python -c "import sys,struct; assert sys.version_info[:2] == (3,11) and struct.calcsize('P') == 8"
if ($LASTEXITCODE -ne 0) { throw '64-bit Python 3.11 required for this reviewed runtime profile.' }
$disk = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($base))
if ($disk.AvailableFreeSpace -lt 10GB) { throw 'At least 10 GiB free disk required for installation.' }
if (!(Test-Path -LiteralPath $base)) { New-Item -ItemType Directory -Path $base | Out-Null }
$item = Get-Item -LiteralPath $base
if (!$item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Unsafe runtime directory.' }
$mutex = [Threading.Mutex]::new($false, ('Local\CyberbotAISetup-' + [Security.Principal.WindowsIdentity]::GetCurrent().User.Value))
$owned = $false
try {
    try { $owned = $mutex.WaitOne(0) }
    catch [Threading.AbandonedMutexException] { $owned = $true }
    if (!$owned) { throw 'Another setup is running.' }
    foreach ($plan in $plans) {
        $target = Join-Path $base $plan.Name
        if (Test-Path -LiteralPath $target) {
            Write-Host ('PRESERVED_EXISTING: ' + $plan.Name + ' ; review separately')
            continue
        }
        # venvs are not relocatable: create at final path, never rename a venv.
        New-Item -ItemType Directory -Path $target -ErrorAction Stop | Out-Null
        $marker = Join-Path $target '.setup-incomplete'
        [IO.File]::WriteAllText($marker,'Do not use until setup validation succeeds.')
        & $python -m venv $target
        if ($LASTEXITCODE -ne 0) { throw ('venv creation failed: ' + $plan.Name) }
        $runtime = Join-Path $target 'Scripts\python.exe'
        $packages = @($plan.Package)
        & $runtime -m pip --isolated install --index-url https://pypi.org/simple --only-binary=:all: --no-input --disable-pip-version-check --timeout 30 --retries 1 @packages
        if ($LASTEXITCODE -ne 0) { throw ('Install failed; incomplete runtime retained for manual review: ' + $plan.Name) }
        & $runtime -m pip check
        if ($LASTEXITCODE -ne 0) { throw 'Dependency check failed.' }
        $verify = 'import importlib.metadata as m; import importlib; import sys; importlib.import_module(sys.argv[1]); assert m.version(sys.argv[1]) == sys.argv[2]'
        $modules = @($plan.Module)
        $versions = @($plan.Version)
        for ($i=0; $i -lt $modules.Count; $i++) {
            & $runtime -c $verify $modules[$i] $versions[$i]
            if ($LASTEXITCODE -ne 0) { throw 'Native import or version check failed.' }
        }
        Remove-Item -LiteralPath $marker
        Write-Host ('RUNTIME_IMPORT_OK: ' + $plan.Name)
    }
    Write-Host 'No tasks enabled. Native model smoke tests and data permission review are still required.'
} finally {
    if ($owned) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
