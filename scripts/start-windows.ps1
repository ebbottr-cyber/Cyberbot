# Local foreground service. No firewall changes, no scheduled tasks.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    $python = Join-Path $root '.venv\Scripts\python.exe'
    if (-not (Test-Path $python)) { throw 'Run setup-windows.ps1 first.' }
    $env:CYBERBOT_TAILSCALE_ENABLED = '0'
    $env:CYBERBOT_TAILSCALE_WRITE = '0'
    $env:CYBERBOT_SOLANA_READ_ENABLED = '0'
    $env:CYBERBOT_LOCAL_LLM_ENABLED = '0'
    $env:CYBERBOT_CHRONOS_ENABLED = '0'
    $env:CYBERBOT_DB = Join-Path $root 'var\paper.sqlite3'
    $env:CYBERBOT_LEARNING_DB = Join-Path $root 'var\learning.sqlite3'
    New-Item -ItemType Directory -Force 'var\logs' | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    # Do not write URL query strings or request headers to the log.
    $log = Join-Path $root "var\logs\server-$stamp.log"
    Write-Host 'Obsidian: http://127.0.0.1:8765 (Ctrl+C to stop)'
    & $python -m uvicorn cyberbot.api:app --host 127.0.0.1 --port 8765 --no-proxy-headers --no-access-log 2>&1 | ForEach-Object { $_ | Out-File -FilePath $log -Append -Encoding utf8; Write-Host $_ }
    if ($LASTEXITCODE -ne 0) { throw 'Cyberbot exited with an error.' }
} finally { Pop-Location }
