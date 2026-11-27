# Futures-only setup and foreground launch. Default mode is a read-only preview.
[CmdletBinding()]
param(
    [ValidateSet('Preview','Prepare','Status','Probe','SafetyStatus','SafetyProbe','Health','Performance','StrategyGate','Backup','VerifyBackup','StageRecovery','Collect','Evaluate','PaperObserve','Supervise','Watchdog')]
    [string]$Mode = 'Preview',
    [ValidateSet('BTCUSDT','ETHUSDT')][string]$Symbol = 'BTCUSDT',
    [ValidateRange(1,1440)][int]$Cycles = 1200,
    [switch]$ConfirmDataRights,
    [switch]$ConfirmPaperObservation,
    [switch]$RecordPredictions,
    [switch]$ConfirmAutoPaper,
    [string]$BackupRoot,
    [string]$BackupDirectory,
    [switch]$ConfirmBackupRights,
    [switch]$ConfirmOffline
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv-futures\Scripts\python.exe'
$marker = Join-Path $root '.venv-futures\cyberbot-tested-head.txt'
$researchFlags = @('CYBERBOT_FUTURES_LIVE_RESEARCH_ENABLED','CYBERBOT_FUTURES_TRAINING_ENABLED','CYBERBOT_FUTURES_AI_CONSENSUS_ENABLED','CYBERBOT_FUTURES_LIGHTGBM_ENABLED','CYBERBOT_FUTURES_RIVER_ENABLED','CYBERBOT_FUTURES_AI_MEMORY_ENABLED','CYBERBOT_FUTURES_STRATEGY_OPTIMIZER_ENABLED')
$saved = @{}
function Set-TemporaryEnv([string]$Name,[string]$Value) {
    if (-not $saved.ContainsKey($Name)) { $saved[$Name] = [Environment]::GetEnvironmentVariable($Name,'Process') }
    [Environment]::SetEnvironmentVariable($Name,$Value,'Process')
}
function Invoke-PythonChecked {
    & $python @args
    if ($LASTEXITCODE -ne 0) { throw "Python command failed (exit $LASTEXITCODE)." }
}
function Get-CleanHead {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git required.' }
    $dirty = & git status --porcelain --untracked-files=no
    if ($LASTEXITCODE -ne 0 -or $dirty) { throw 'Tracked checkout must be clean; no automatic git changes.' }
    $commit = & git rev-parse HEAD
    if ($LASTEXITCODE -ne 0 -or -not $commit) { throw 'Git HEAD unavailable.' }
    return [string]$commit
}
Push-Location $root
try {
    if (-not (Test-Path -LiteralPath 'cyberbot\futures_live_research.py' -PathType Leaf)) { throw 'Cyberbot checkout required.' }
    if ($Mode -eq 'Preview') {
        [ordered]@{mode='Preview';symbol=$Symbol;venv_exists=(Test-Path -LiteralPath $python -PathType Leaf);test_marker_exists=(Test-Path -LiteralPath $marker -PathType Leaf);writes=$false;network=$false;real_orders=$false;automatic_entry=$false} | ConvertTo-Json
        return
    }
    if ($Mode -eq 'Prepare') {
        $head = Get-CleanHead
        if (Test-Path -LiteralPath $marker) { Remove-Item -LiteralPath $marker -Force }
        if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
            $launcher = Get-Command py.exe -CommandType Application -ErrorAction SilentlyContinue
            if ($launcher) {
                & $launcher.Source -3.12 -m venv .venv-futures
                if ($LASTEXITCODE -ne 0) { & $launcher.Source -3.11 -m venv .venv-futures }
            } else {
                $base = Get-Command python.exe -CommandType Application -ErrorAction Stop
                & $base.Source -I -m venv .venv-futures
            }
            if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Python 3.11/3.12 venv creation failed.' }
        }
        Invoke-PythonChecked -I -c 'import sys; assert sys.version_info[:2] in [(3,11),(3,12)]'
        Invoke-PythonChecked -I -m pip install -r requirements.txt -r requirements-futures-ai.txt
        Invoke-PythonChecked -I -m pip check
        $stage = Join-Path ([IO.Path]::GetTempPath()) ('Cyberbot-futures-' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $stage | Out-Null
        try {
            $archive = Join-Path $stage 'source.zip'
            $testRoot = Join-Path $stage 'source'
            & git archive --format=zip "--output=$archive" $head
            if ($LASTEXITCODE -ne 0) { throw 'Git archive failed.' }
            Expand-Archive -LiteralPath $archive -DestinationPath $testRoot
            foreach ($e in @(Get-ChildItem Env: | Where-Object { $_.Name -like 'CYBERBOT_*' -or $_.Name -in @('PYTHONPATH','PYTHONHOME') })) {
                Set-TemporaryEnv $e.Name $null
            }
            Push-Location $testRoot
            try {
                Invoke-PythonChecked -c 'import lightgbm, river, sklearn, httpx'
                Invoke-PythonChecked -m unittest discover -s tests -v
            } finally { Pop-Location }
        } finally { Remove-Item -LiteralPath $stage -Recurse -Force }
        if ((Get-CleanHead) -ne $head) { throw 'Checkout changed during preparation.' }
        Set-Content -LiteralPath $marker -Value $head -Encoding Ascii
        Write-Host 'Futures preparation passed. No provider or task started.'
        return
    }
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Run -Mode Prepare first.' }
    if ($Mode -eq 'Status') {
        Invoke-PythonChecked -m cyberbot.futures_live_research --symbol $Symbol --status
        return
    }
    if ($Mode -in @('Backup','VerifyBackup','StageRecovery')) {
        if ($Mode -ne 'VerifyBackup') {
            if (-not $ConfirmBackupRights -or -not $BackupRoot) { throw 'Explicit backup rights and destination required.' }
            Set-TemporaryEnv 'CYBERBOT_FUTURES_BACKUP_RIGHTS_CONFIRMED' '1'
        }
        if ($Mode -eq 'Backup') {
            if (-not $ConfirmOffline) { throw 'Stop all writers and confirm offline backup.' }
            Invoke-PythonChecked -m cyberbot.futures_backup backup --root $BackupRoot --offline-confirmed
        } elseif ($Mode -eq 'VerifyBackup') {
            if (-not $BackupDirectory) { throw 'Backup directory required.' }
            Invoke-PythonChecked -m cyberbot.futures_backup verify --directory $BackupDirectory
        } else {
            if (-not $BackupDirectory) { throw 'Backup directory required.' }
            Invoke-PythonChecked -m cyberbot.futures_backup stage --directory $BackupDirectory --root $BackupRoot
        }
        return
    }
    if ($Mode -eq 'StrategyGate') {
        Invoke-PythonChecked -m cyberbot.futures_strategy_gate --symbol $Symbol
        return
    }
    if ($Mode -eq 'Performance') {
        Invoke-PythonChecked -m cyberbot.futures_performance --symbol $Symbol
        return
    }
    if ($Mode -eq 'Health') {
        Invoke-PythonChecked -m cyberbot.futures_health --symbol $Symbol
        return
    }
    if ($Mode -eq 'SafetyStatus') {
        Invoke-PythonChecked -m cyberbot.futures_safety --symbol $Symbol
        return
    }
    $head = Get-CleanHead
    if (-not (Test-Path -LiteralPath $marker -PathType Leaf) -or ((Get-Content -LiteralPath $marker -Raw).Trim() -ne $head)) {
        throw 'Run -Mode Prepare for this exact commit before launching.'
    }
    Invoke-PythonChecked -I -m pip check
    if (-not $ConfirmDataRights) { throw 'Explicit -ConfirmDataRights required after checking provider data rights.' }
    Set-TemporaryEnv 'CYBERBOT_BINANCE_OBSERVED_ENABLED' '1'
    Set-TemporaryEnv 'CYBERBOT_BINANCE_DATA_RIGHTS_CONFIRMED' '1'
    Set-TemporaryEnv 'CYBERBOT_FUTURES_PILOT_SYMBOL' $Symbol
    if ($Mode -eq 'SafetyProbe') {
        Set-TemporaryEnv 'CYBERBOT_FUTURES_SAFETY_PROBE_ENABLED' '1'
        Invoke-PythonChecked -m cyberbot.futures_safety --symbol $Symbol --probe
        return
    }
    if ($Mode -eq 'Probe') {
        Invoke-PythonChecked -c 'import json; from cyberbot.providers.binance_observed import run; print(json.dumps(run(apply=False),ensure_ascii=True))'
        return
    }
    if ($Mode -eq 'PaperObserve') {
        if (-not $ConfirmPaperObservation) { throw 'Explicit -ConfirmPaperObservation required: existing manual intents can be filled.' }
        if ($env:CYBERBOT_OBSERVED_PRICE_RIGHTS_CONFIRMED -ne '1' -or $env:CYBERBOT_OBSERVED_PILOT_ENABLED -ne '1' -or $env:CYBERBOT_FUTURES_PILOT_ENABLED -ne '1' -or $env:CYBERBOT_PILOT_INGRESS_ENABLED -ne '1' -or $env:CYBERBOT_INGRESS_SOURCE_FUTURES -ne 'binance-usdm-public') { throw 'Existing paper pilot permissions and source must be configured separately.' }
        Set-TemporaryEnv 'CYBERBOT_FUTURES_LIVE_RESEARCH_ENABLED' '1'
        Set-TemporaryEnv 'CYBERBOT_FUTURES_LIVE_PAPER_OBSERVE_ENABLED' '1'
        Invoke-PythonChecked -m cyberbot.futures_live_research --symbol $Symbol --paper-observe
        return
    }
    foreach ($flag in $researchFlags) { Set-TemporaryEnv $flag '1' }
    if ($Mode -in @('Supervise','Watchdog')) {
        Set-TemporaryEnv 'CYBERBOT_FUTURES_DIAGNOSTICS_ENABLED' '1'
        Set-TemporaryEnv 'CYBERBOT_FUTURES_SUPERVISOR_ENABLED' '1'
        Set-TemporaryEnv 'CYBERBOT_FUTURES_FORWARD_MEMORY_ENABLED' '1'
        $module = 'cyberbot.futures_supervisor'
        if ($Mode -eq 'Watchdog') {
            Set-TemporaryEnv 'CYBERBOT_FUTURES_WATCHDOG_ENABLED' '1'
            $module = 'cyberbot.futures_watchdog'
        }
        $arguments = @('-m',$module,'--symbol',$Symbol,'--minutes',$Cycles)
        if ($ConfirmPaperObservation) {
            Set-TemporaryEnv 'CYBERBOT_FUTURES_SUPERVISOR_PAPER_CONFIRMED' '1'
            $arguments += '--paper'
        }
        if ($ConfirmAutoPaper) {
            if (-not $ConfirmPaperObservation) { throw 'Separate paper observation confirmation required.' }
            Set-TemporaryEnv 'CYBERBOT_FUTURES_AUTO_PAPER_ENABLED' '1'
            Set-TemporaryEnv 'CYBERBOT_FUTURES_AUTO_PAPER_CONFIRMED' '1'
            Set-TemporaryEnv 'CYBERBOT_FUTURES_AI_BRIDGE_ENABLED' '1'
            $arguments += '--automatic'
        }
        Invoke-PythonChecked @arguments
        return
    }
    if ($Mode -eq 'Collect') {
        $arguments = @('-m','cyberbot.futures_live_research','--symbol',$Symbol,'--collect-cycles',$Cycles)
        if ($RecordPredictions) {
            Set-TemporaryEnv 'CYBERBOT_FUTURES_FORWARD_MEMORY_ENABLED' '1'
            $arguments += '--record-predictions'
        }
        Invoke-PythonChecked @arguments
    } elseif ($Mode -eq 'Evaluate') {
        Invoke-PythonChecked -m cyberbot.futures_live_research --symbol $Symbol --evaluate
    }
} finally {
    foreach ($name in $saved.Keys) { [Environment]::SetEnvironmentVariable($name,$saved[$name],'Process') }
    Pop-Location
}
