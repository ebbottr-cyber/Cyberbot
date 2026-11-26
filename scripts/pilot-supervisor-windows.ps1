# Foreground or explicitly registered logon task. Rights must already be configured.
param([switch]$Continuous)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    $python = Join-Path $root '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Run setup-windows.ps1 first.' }
    if ($env:CYBERBOT_PILOT_SUPERVISOR_ENABLED -ne '1') { throw 'Supervisor permission is not enabled.' }
    $arguments = @('-m','tools.pilot_supervisor')
    if ($Continuous) { $arguments += '--continuous' }
    & $python @arguments
    exit $LASTEXITCODE
} finally { Pop-Location }
