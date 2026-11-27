# Local Windows readiness audit; no installs, database writes, task changes, or network calls.
param([switch]$CheckImports)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$base = Join-Path $env:LOCALAPPDATA 'Cyberbot'
$folder = Join-Path $root 'var\ai'
$checks = [Collections.Generic.List[object]]::new()
function Add-Check($name,$state) {
    $checks.Add([ordered]@{name=$name;status=$state})
}
$plans = @(
    @{Name='Chronos'; Path=(Join-Path $base 'ChronosRuntime'); Module='chronos'; Dist='chronos-forecasting'; Version=''},
    @{Name='LightGBM'; Path=(Join-Path $base 'LightGBMRuntime'); Module='lightgbm'; Dist='lightgbm'; Version='4.6.0'},
    @{Name='River'; Path=(Join-Path $base 'RiverRuntime'); Module='river'; Dist='river'; Version='0.23.0'},
    @{Name='ReviewRuntime-LightGBM'; Path=(Join-Path $base 'ReviewRuntime'); Module='lightgbm'; Dist='lightgbm'; Version='4.6.0'},
    @{Name='ReviewRuntime-River'; Path=(Join-Path $base 'ReviewRuntime'); Module='river'; Dist='river'; Version='0.23.0'}
)
foreach ($plan in $plans) {
    $py = Join-Path $plan.Path 'Scripts\python.exe'
    $state = 'PRESENT_NOT_TESTED'
    if (!(Test-Path -LiteralPath $py -PathType Leaf)) { $state='MISSING' }
    elseif (Test-Path -LiteralPath (Join-Path $plan.Path '.setup-incomplete')) { $state='INCOMPLETE' }
    elseif ($CheckImports) {
        # Isolated Python startup; imports are local, not model downloads.
        $env:HF_HUB_OFFLINE='1'
        $env:TRANSFORMERS_OFFLINE='1'
        $env:HF_HUB_DISABLE_TELEMETRY='1'
        $env:CUDA_VISIBLE_DEVICES=''
        $code = 'import sys,importlib,importlib.metadata as m; importlib.import_module(sys.argv[1]); assert sys.argv[3] == "any" or m.version(sys.argv[2]) == sys.argv[3]'
        $v = if ($plan.Version) { $plan.Version } else { 'any' }
        & $py -I -B -c $code $plan.Module $plan.Dist $v 2>$null | Out-Null
        $state = if ($LASTEXITCODE -eq 0) {'IMPORT_OK'} else {'IMPORT_FAILED'}
    }
    Add-Check $plan.Name $state
}
$mainPython = Join-Path $root '.venv\Scripts\python.exe'
Add-Check 'MainPython' $(if (Test-Path -LiteralPath $mainPython -PathType Leaf) {'PRESENT_NOT_TESTED'} else {'MISSING'})
Add-Check 'ResearchRights' $(if ($env:CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED -eq '1') {'CONFIRMED_BY_OPERATOR'} else {'NOT_CONFIRMED'})
$disk = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($root))
$runtimeDisk = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($base))
$os = Get-CimInstance -ClassName Win32_OperatingSystem
Add-Check 'RuntimeInstallDisk' $(if ($runtimeDisk.AvailableFreeSpace -ge 10GB) {'OK'} else {'WAIT_DISK'})
$cpuLoad = $null
try {
    $loads = @(Get-CimInstance -ClassName Win32_Processor -ErrorAction Stop | ForEach-Object { $_.LoadPercentage })
    if ($loads.Count -gt 0 -and @($loads | Where-Object { $null -eq $_ -or $_ -lt 0 -or $_ -gt 100 }).Count -eq 0) {
        $cpuLoad = [math]::Round(($loads | Measure-Object -Average).Average,2)
    }
} catch { }
Add-Check 'CPUAdmission' $(if ($null -eq $cpuLoad) {'UNKNOWN'} elseif ($cpuLoad -lt 70) {'OK'} else {'WAIT_CPU'})
Add-Check 'DiskReserve' $(if ($disk.AvailableFreeSpace -ge 5GB) {'OK'} else {'WAIT_DISK'})
Add-Check 'RAMAdmission' $(if ($null -ne $os.FreePhysicalMemory -and [uint64]$os.FreePhysicalMemory -ge 5242880) {'OK'} else {'WAIT_MEMORY'})
$runtimeState = 'MISSING'
if (Test-Path -LiteralPath $folder -PathType Container) {
    $report = Get-ChildItem -LiteralPath $folder -File -Filter 'chronos-runtime-*.json' | Sort-Object Name -Descending | Select-Object -First 1
    if ($report) {
        $runtimeState = 'REVIEW_REQUIRED'
        try {
            if ($report.Length -gt 65536 -or ($report.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Unsafe report.' }
            $r = Get-Content -LiteralPath $report.FullName -Raw | ConvertFrom-Json
            if ($r.runtime_verified -eq $true -and $r.model_path -and [IO.Path]::IsPathRooted([string]$r.model_path) -and (Test-Path -LiteralPath $r.model_path -PathType Container)) {
                $config = Join-Path $r.model_path 'config.json'
                $weights = @(Get-ChildItem -LiteralPath $r.model_path -File -Filter '*.safetensors')
                if ((Test-Path -LiteralPath $config -PathType Leaf) -and $weights.Count -gt 0) {
                    $runtimeState = 'REPORT_AND_FILES_PRESENT_NOT_RETESTED'
                }
            }
        } catch { $runtimeState='REVIEW_REQUIRED' }
    }
}
Add-Check 'ChronosModel' $runtimeState
Add-Check 'ForwardJournal' $(if (Test-Path -LiteralPath (Join-Path $folder 'forward-models-v2.sqlite3') -PathType Leaf) {'PRESENT_NOT_VALIDATED'} else {'MISSING'})
foreach ($name in @('Chronos','RiverLive','RiverReplay','LightGBM','ForwardBackup','Watchdog','ResearchReview')) {
    $task = Get-ScheduledTask -TaskPath '\' -TaskName ('Cyberbot-AI-'+$name) -ErrorAction SilentlyContinue
    Add-Check ('Task-'+$name) $(if ($null -eq $task) {'NOT_REGISTERED'} else {[string]$task.State})
}
[ordered]@{
    version='ai-readiness-2'
    checked_at_utc=[DateTime]::UtcNow.ToString('o')
    status='MANUAL_REVIEW_REQUIRED'
    free_disk_gib=[math]::Round($disk.AvailableFreeSpace / 1GB,2)
    free_ram_gib=[math]::Round([double]$os.FreePhysicalMemory / 1MB,2)
    runtime_disk_free_gib=[math]::Round($runtimeDisk.AvailableFreeSpace / 1GB,2)
    cpu_load_pct=$cpuLoad
    import_checks_requested=[bool]$CheckImports
    imports_are_not_inference_tests=$true
    checks=$checks.ToArray()
    native_inference_verified=$false
    paper_readiness_verified=$false
    tasks_modified=$false
    real_orders=$false
} | ConvertTo-Json -Depth 5
