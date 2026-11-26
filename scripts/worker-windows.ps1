# Explicit foreground research loop; does not start or control the paper ledger.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    $python = Join-Path $root '.venv\Scripts\python.exe'
    if (-not (Test-Path $python)) { throw 'Run setup-windows.ps1 first.' }
    $env:CYBERBOT_DB = Join-Path $root 'var\paper.sqlite3'
    $env:CYBERBOT_LEARNING_DB = Join-Path $root 'var\learning.sqlite3'
    $env:CYBERBOT_WORKER_DB = Join-Path $root 'var\worker.sqlite3'
    $env:CYBERBOT_SOLANA_READ_ENABLED = '0'
    $env:CYBERBOT_LOCAL_LLM_ENABLED = '0'
    $env:CYBERBOT_CHRONOS_ENABLED = '0'
    & $python -m tools.worker --loop --interval 900 --full-research
    if ($LASTEXITCODE -ne 0) { throw 'Research worker exited.' }
} finally { Pop-Location }
