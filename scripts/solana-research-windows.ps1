# Bounded, explicit Solana research only. Run in a dedicated Git worktree.
param(
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$DexTermRoot,
    [Parameter(Mandatory=$true)][string]$DataRoot,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$ExpectedCommit,
    [switch]$ConfirmDataRights,
    [switch]$StartResearch,
    [switch]$EnableModels
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $StartResearch -or -not $ConfirmDataRights) { throw 'Explicit research and data rights opt-in required.' }
if (-not (Test-Path -LiteralPath (Join-Path $root '.git') -PathType Leaf)) { throw 'Dedicated Git worktree required.' }
$Python = (Resolve-Path -LiteralPath $Python).ProviderPath
$DexTermRoot = (Resolve-Path -LiteralPath $DexTermRoot).ProviderPath
$DataRoot = (Resolve-Path -LiteralPath $DataRoot).ProviderPath
$db = Join-Path $DataRoot 'solana-research.sqlite3'
$history = Join-Path $DataRoot 'solana-model-history.sqlite3'
$reports = Join-Path $DataRoot 'reports'
$logs = Join-Path $DataRoot 'logs'
$stop = $db + '.research.stop'
if (Test-Path -LiteralPath $stop) { Write-Host 'Research stopped; review the stop marker manually.'; exit 2 }
Push-Location $root
try {
    $head = & git rev-parse HEAD
    if ($LASTEXITCODE -ne 0 -or $head -ne $ExpectedCommit) { throw 'Checkout revision differs from validated revision.' }
    $changes = & git status --porcelain --untracked-files=no
    if ($LASTEXITCODE -ne 0 -or $changes) { throw 'Tracked checkout files are modified.' }
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'Python missing.' }
    New-Item -ItemType Directory -Path $reports,$logs -Force | Out-Null
    # Only this process and its children receive these settings.
    $env:CYBERBOT_PILOT_KILL_SWITCH = '1'
    $env:CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED = '1'
    $env:OMP_NUM_THREADS = '1'
    $env:OPENBLAS_NUM_THREADS = '1'
    $env:MKL_NUM_THREADS = '1'
    $env:NUMEXPR_NUM_THREADS = '1'
    $env:PYTHONNOUSERSITE = '1'
    $arguments = @('-m','tools.solana_research_scheduler','--enable-research-scheduler','--cycles','1',
        '--database',$db,'--history-database',$history,'--report-dir',$reports,
        '--dexterm-root',$DexTermRoot,'--window-hours','24','--publish-pwa')
    if ($EnableModels) { $arguments += @('--allow-experiment','--include-lightgbm','--include-river','--include-adaptive') }
    $log = Join-Path $logs ('cycle-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N') + '.log')
    $healthLog = $log + '.health.json'
    & $Python -m tools.solana_pc_health --data-root $DataRoot --preflight *> $healthLog
    if ($LASTEXITCODE -ne 0) { throw 'Research resource preflight blocked. See health report.' }
    & $Python @arguments *> $log
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw ('Research cycle exit code: ' + $code) }
    exit 0
} catch {
    # No automatic retries after a failed research cycle or changed checkout.
    if (-not (Test-Path -LiteralPath $stop)) {
        New-Item -ItemType File -Path $stop -ErrorAction Stop | Out-Null
    }
    Write-Error 'Solana research halted. Review the isolated logs and stop marker before restarting.' -ErrorAction Continue
    exit 1
} finally { Pop-Location }
