# Run from an existing Cyberbot checkout; no changes outside its folder.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    if (-not (Test-Path 'requirements.txt') -or -not (Test-Path 'cyberbot\api.py')) { throw 'Cyberbot checkout required.' }
    if (-not (Test-Path '.venv\Scripts\python.exe')) {
        if (Get-Command py -ErrorAction SilentlyContinue) { & py -3.12 -m venv .venv; if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 required (or create a 3.11 venv manually).' } }
        else { & python -m venv .venv; if ($LASTEXITCODE -ne 0) { throw 'Python environment failed.' } }
    }
    $python = Join-Path $root '.venv\Scripts\python.exe'
    & $python -c "import sys; assert sys.version_info[:2] in [(3,11),(3,12)]"
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or 3.12 required.' }
    & $python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency install failed.' }
    & $python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed; do not start.' }
    Write-Host 'Setup complete. Run scripts/start-windows.ps1.'
} finally { Pop-Location }
