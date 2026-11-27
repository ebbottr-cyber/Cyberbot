# Single entry point for local Obsidian preparation and panel startup.
[CmdletBinding()]
param(
    [ValidateSet('Preview','Prepare','Status','StartPanel')]
    [string]$Mode = 'Preview',
    [switch]$ConnectNotifications
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$marker = Join-Path $root '.venv\cyberbot-central-tested-head.txt'
$saved = @{}
function Set-ScopedEnv([string]$Name,$Value) {
    if (-not $saved.ContainsKey($Name)) { $saved[$Name] = [Environment]::GetEnvironmentVariable($Name,'Process') }
    [Environment]::SetEnvironmentVariable($Name,$Value,'Process')
}
function Get-CleanHead {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git required.' }
    $dirty = & git status --porcelain --untracked-files=no
    if ($LASTEXITCODE -ne 0 -or $dirty) { throw 'Tracked checkout must be clean.' }
    $extra = & git ls-files --others --exclude-standard -- cyberbot tools scripts tests
    if ($LASTEXITCODE -ne 0 -or $extra) { throw 'Untracked source must be reviewed.' }
    $head = & git rev-parse HEAD
    if ($LASTEXITCODE -ne 0 -or $head -notmatch '^[a-f0-9]{40}$') { throw 'Git HEAD unavailable.' }
    return [string]$head
}
Push-Location $root
try {
    if (-not (Test-Path -LiteralPath 'cyberbot\integration_api.py' -PathType Leaf)) { throw 'Central integration checkout required.' }
    if ($Mode -eq 'Preview') {
        [ordered]@{mode='Preview';venv_exists=(Test-Path -LiteralPath $python -PathType Leaf);test_marker_exists=(Test-Path -LiteralPath $marker -PathType Leaf);panel='http://127.0.0.1:8765';writes=$false;network=$false;starts_services=$false;real_orders=$false} | ConvertTo-Json
        return
    }
    $head = Get-CleanHead
    if ($Mode -eq 'Prepare') {
        if (Test-Path -LiteralPath $marker) { Remove-Item -LiteralPath $marker -Force }
        & (Join-Path $PSScriptRoot 'prepare-pilot-windows.ps1') -Prepare
        if ($LASTEXITCODE -ne 0) { throw 'Preparation failed.' }
        if ((Get-CleanHead) -ne $head) { throw 'Checkout changed during preparation.' }
        Set-Content -LiteralPath $marker -Value $head -Encoding Ascii
        Write-Host 'Base preparation passed. Optional AI/DexTerm runtimes are separate.'
        return
    }
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Run -Mode Prepare first.' }
    if ($Mode -eq 'Status') {
        & (Join-Path $PSScriptRoot 'prepare-pilot-windows.ps1')
        if ($LASTEXITCODE -ne 0) { throw 'Status failed.' }
        return
    }
    if (-not (Test-Path -LiteralPath $marker -PathType Leaf) -or ((Get-Content -LiteralPath $marker -Raw).Trim() -ne $head)) { throw 'Run -Mode Prepare for this exact commit.' }
    # No automatic worker, network provider or remote access starts from this launcher.
    # Preserve only reviewed local read inputs, not inherited activation flags.
    $keep = @('CYBERBOT_EBBOT_DB','CYBERBOT_EQUITY_RESEARCH_RIGHTS_CONFIRMED','CYBERBOT_FX_FILE','CYBERBOT_DEXTERM_ARCHIVE','CYBERBOT_DEXTERM_REPLAY_REPORT','CYBERBOT_NOTIFICATION_HEALTH_FILE','CYBERBOT_NOTIFICATION_DB','CYBERBOT_RESEARCH_NEWS_DB','CYBERBOT_AI_PANEL_ENABLED','CYBERBOT_OBSERVED_PILOT_ENABLED','CYBERBOT_OBSERVED_PRICE_RIGHTS_CONFIRMED','CYBERBOT_FUTURES_PILOT_ENABLED','CYBERBOT_FUTURES_PILOT_SYMBOL','CYBERBOT_OBSERVED_FX_RIGHTS_CONFIRMED','CYBERBOT_PILOT_DB')
    foreach ($e in @(Get-ChildItem Env: | Where-Object { ($_.Name -like 'CYBERBOT_*' -and $_.Name -notin $keep) -or $_.Name -in @('PYTHONPATH','PYTHONHOME') })) {
        Set-ScopedEnv $e.Name $null
    }
    if ($ConnectNotifications) {
        $state = Join-Path $HOME '.cyberbot-private'
        Set-ScopedEnv 'CYBERBOT_NOTIFICATION_HEALTH_FILE' (Join-Path $state 'notification-health.json')
        Set-ScopedEnv 'CYBERBOT_NOTIFICATION_DB' (Join-Path $state 'notifications.sqlite3')
        Set-ScopedEnv 'CYBERBOT_RESEARCH_NEWS_DB' (Join-Path $state 'research-news.sqlite3')
    }
    Set-ScopedEnv 'CYBERBOT_PILOT_KILL_SWITCH' '1'
    Set-ScopedEnv 'CYBERBOT_DB' (Join-Path $root 'var\paper.sqlite3')
    Set-ScopedEnv 'CYBERBOT_LEARNING_DB' (Join-Path $root 'var\learning.sqlite3')
    & $python -I -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Dependency conflict.' }
    & $python -c 'from cyberbot.db_paths import checked; checked()'
    if ($LASTEXITCODE -ne 0) { throw 'Database path validation failed.' }
    & powershell.exe -NoProfile -File (Join-Path $PSScriptRoot 'start-windows.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Panel stopped with error.' }
} finally {
    foreach ($name in $saved.Keys) { [Environment]::SetEnvironmentVariable($name,$saved[$name],'Process') }
    Pop-Location
}
