# One-command preparation in an existing dedicated Git worktree. Never enables a task.
param(
    [Parameter(Mandatory=$true)][string]$DexTermRoot,
    [string]$Python = (Join-Path (Split-Path -Parent $PSScriptRoot) '.venv\Scripts\python.exe'),
    [string]$DataRoot = (Join-Path $env:LOCALAPPDATA 'Cyberbot-Solana-Research'),
    [switch]$EnableModels,
    [switch]$RegisterDisabledTask,
    [switch]$ConfirmDataRights
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if ($env:OS -ne 'Windows_NT') { throw 'Windows required.' }
if ($RegisterDisabledTask -and -not $ConfirmDataRights) { throw 'Explicit provider data rights confirmation required.' }
if (-not (Test-Path -LiteralPath (Join-Path $root '.git') -PathType Leaf)) { throw 'Run only from a dedicated Git worktree.' }
$Python = (Resolve-Path -LiteralPath $Python).ProviderPath
$DexTermRoot = (Resolve-Path -LiteralPath $DexTermRoot).ProviderPath
$DataRoot = [IO.Path]::GetFullPath($DataRoot)
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'Python interpreter missing.' }
if (-not (Test-Path -LiteralPath $DexTermRoot -PathType Container)) { throw 'DexTerm checkout missing.' }
if ($DataRoot.Equals($root,[StringComparison]::OrdinalIgnoreCase) -or
    $DataRoot.StartsWith($root.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Data directory must be outside checkout.' }
if (Test-Path -LiteralPath $DataRoot) {
    if (-not (Test-Path -LiteralPath $DataRoot -PathType Container)) { throw 'Data directory is not a directory.' }
    if ((Get-Item -LiteralPath $DataRoot).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Data directory must not be a junction or symlink.' }
}
$name = 'Cyberbot-Solana-Research'
if ($RegisterDisabledTask -and (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue)) { throw 'Existing task not overwritten.' }
Push-Location $root
try {
    $head = & git rev-parse HEAD
    if ($LASTEXITCODE -ne 0 -or $head -notmatch '^[0-9a-f]{40}$') { throw 'Git revision invalid.' }
    $changes = & git status --porcelain --untracked-files=no
    if ($LASTEXITCODE -ne 0 -or $changes) { throw 'Tracked files modified.' }
    $dexHead = & git -C $DexTermRoot rev-parse HEAD
    if ($LASTEXITCODE -ne 0 -or $dexHead -ne '235a55e71f90ee5ba32d05ec11d90570ddd079c2') { throw 'DexTerm revision mismatch.' }
    $dexChanges = & git -C $DexTermRoot status --porcelain --untracked-files=no
    if ($LASTEXITCODE -ne 0 -or $dexChanges) { throw 'DexTerm tracked files modified.' }
    if (-not (Test-Path -LiteralPath (Join-Path $DexTermRoot 'packages\mcp\bin\dexterm-mcp.mjs') -PathType Leaf)) { throw 'DexTerm MCP entry missing.' }
    if (-not (Test-Path -LiteralPath (Join-Path $DexTermRoot 'node_modules') -PathType Container)) { throw 'DexTerm dependencies missing; no installation attempted.' }
    $node = Get-Command node.exe -ErrorAction Stop
    $nodeVersion = & $node.Source --version
    if ($LASTEXITCODE -ne 0 -or $nodeVersion -notmatch '^v(\d+\.\d+\.\d+)$') { throw 'Node version unavailable.' }
    if ([version]$Matches[1] -lt [version]'22.18.0') { throw 'Node 22.18 or newer required.' }
    foreach ($file in @('prepare-solana-windows.ps1','register-solana-research-windows.ps1','solana-research-windows.ps1')) {
        $tokens = $null; $errors = $null
        [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot $file),[ref]$tokens,[ref]$errors) | Out-Null
        if ($errors.Count -gt 0) { throw ('PowerShell syntax validation failed: ' + $file) }
    }
    & $Python -I -c "import sys,fastapi,httpx,uvicorn; assert sys.version_info >= (3,10)"
    if ($LASTEXITCODE -ne 0) { throw 'Python or required dependencies unavailable; no installation attempted.' }
    # Registration repeats the tests itself, so only run the standalone checks when not registering.
    if ($RegisterDisabledTask) {
        $registration = @{
            Python = $Python
            DexTermRoot = $DexTermRoot
            DataRoot = $DataRoot
            Register = $true
            ConfirmDataRights = $true
            EnableModels = [bool]$EnableModels
        }
        & (Join-Path $PSScriptRoot 'register-solana-research-windows.ps1') @registration
        $task = Get-ScheduledTask -TaskName $name -ErrorAction Stop
        if ($task.State -ne 'Disabled') { throw 'Unexpected task state; review before any use.' }
    } else {
        & $Python -m tools.solana_offline_test_suite
        if ($LASTEXITCODE -ne 0) { throw 'Offline validation failed.' }
        if ($EnableModels) {
            & $Python -m tools.solana_native_model_check --allow-synthetic-fit
            if ($LASTEXITCODE -ne 0) { throw 'Native model validation failed.' }
        }
    }
    [ordered]@{
        status = 'preparation_complete'
        validated_commit = $head
        dexterm_revision = $dexHead
        node_version = $nodeVersion
        native_models_requested = [bool]$EnableModels
        disabled_task_registered = [bool]$RegisterDisabledTask
        task_started = $false
        live_provider_verified = $false
        real_orders = $false
        pwa_data_root = $DataRoot
        pwa_report_dir = (Join-Path $DataRoot 'reports')
    } | ConvertTo-Json
} finally { Pop-Location }
