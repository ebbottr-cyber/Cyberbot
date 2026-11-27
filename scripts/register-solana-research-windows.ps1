# Preview by default. Creates only a disabled, limited, interactive Solana task.
param(
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$DexTermRoot,
    [string]$DataRoot = (Join-Path $env:LOCALAPPDATA 'Cyberbot-Solana-Research'),
    [switch]$Register,
    [switch]$ConfirmDataRights,
    [switch]$EnableModels
)
$ErrorActionPreference = 'Stop'
$name = 'Cyberbot-Solana-Research'
$root = Split-Path -Parent $PSScriptRoot
if (-not $Register) { Write-Host 'Preview only. No files or task created. Registration requires explicit data rights confirmation and passing tests.'; return }
if (-not $ConfirmDataRights) { throw 'Confirm permitted provider data use before registration.' }
if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) { throw 'Solana task already exists; not overwritten.' }
if (-not (Test-Path -LiteralPath (Join-Path $root '.git') -PathType Leaf)) { throw 'Use a dedicated Git worktree.' }
$Python = (Resolve-Path -LiteralPath $Python).ProviderPath
$DexTermRoot = (Resolve-Path -LiteralPath $DexTermRoot).ProviderPath
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'Python missing.' }
if (-not (Test-Path -LiteralPath $DexTermRoot -PathType Container)) { throw 'DexTerm checkout missing.' }
$DataRoot = [System.IO.Path]::GetFullPath($DataRoot)
# Dedicated data directory; do not reuse a production DB directory.
if (Test-Path -LiteralPath $DataRoot) {
    $DataRoot = (Resolve-Path -LiteralPath $DataRoot).ProviderPath
    if ((Get-Item -LiteralPath $DataRoot).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Data directory must not be a junction or symlink.' }
}
if ($DataRoot.Equals($root,[StringComparison]::OrdinalIgnoreCase) -or
    $DataRoot.StartsWith($root.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Data directory must be outside checkout.' }
foreach ($v in @($Python,$DexTermRoot,$DataRoot,$root)) {
    if ($v -match '["\r\n]') { throw 'Unsupported path characters.' }
}
Push-Location $root
try {
    $head = & git rev-parse HEAD
    if ($LASTEXITCODE -ne 0 -or $head -notmatch '^[0-9a-f]{40}$') { throw 'Cannot validate Git revision.' }
    $changes = & git status --porcelain --untracked-files=no
    if ($LASTEXITCODE -ne 0 -or $changes) { throw 'Tracked checkout files are modified.' }
    & $Python -m tools.solana_offline_test_suite
    if ($LASTEXITCODE -ne 0) { throw 'Offline validation failed. Task not created.' }
    if ($EnableModels) {
        & $Python -m tools.solana_native_model_check --allow-synthetic-fit
        if ($LASTEXITCODE -ne 0) { throw 'Native model validation failed. Task not created.' }
    }
    if ((& git rev-parse HEAD) -ne $head -or $LASTEXITCODE -ne 0) { throw 'Checkout changed during validation.' }
    $changes = & git status --porcelain --untracked-files=no
    if ($LASTEXITCODE -ne 0 -or $changes) { throw 'Checkout changed during validation.' }
    New-Item -ItemType Directory -Path $DataRoot -Force | Out-Null
    $script = Join-Path $root 'scripts\solana-research-windows.ps1'
    $argsText = '-NoProfile -NonInteractive -File "' + $script + '" -Python "' + $Python +
        '" -DexTermRoot "' + $DexTermRoot + '" -DataRoot "' + $DataRoot +
        '" -ExpectedCommit "' + $head + '" -StartResearch -ConfirmDataRights'
    if ($EnableModels) { $argsText += ' -EnableModels' }
    $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argsText -WorkingDirectory $root
    $logon = New-ScheduledTaskTrigger -AtLogOn -User $user
    $repeat = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) -RepetitionInterval ([TimeSpan]::FromMinutes(5)) -RepetitionDuration ([TimeSpan]::FromDays(365))
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -Disable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::FromMinutes(15))
    Register-ScheduledTask -TaskName $name -Action $action -Trigger @($logon,$repeat) -Principal $principal -Settings $settings -Description 'Isolated Solana research; no actual trades. Explicit enable required.' | Out-Null
    Write-Host 'Created disabled Solana task. No task started. Review paths and configuration before explicit enablement.'
} finally { Pop-Location }
