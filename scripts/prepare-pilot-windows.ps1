# Default: read-only preflight. -Prepare installs only project dependencies and runs isolated tests.
param([switch]$Prepare)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    if (-not (Test-Path -LiteralPath 'requirements.txt' -PathType Leaf) -or -not (Test-Path -LiteralPath 'cyberbot\pilot_preflight.py' -PathType Leaf)) { throw 'Cyberbot checkout required.' }
    $python = Join-Path $root '.venv\Scripts\python.exe'
    if ($Prepare) {
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git required for isolated source snapshot.' }
        $dirty = & git status --porcelain --untracked-files=no
        if ($LASTEXITCODE -ne 0 -or $dirty) { throw 'Tracked checkout must be clean before preparation.' }
        if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
            & py -3.12 -m venv .venv
            if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 venv creation failed.' }
        }
        & $python -c "import sys; assert sys.version_info[:2] in [(3,11),(3,12)]"
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or 3.12 required.' }
        & $python -m pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
        & $python -m pip check
        if ($LASTEXITCODE -ne 0) { throw 'Dependency conflict.' }
        $stage = Join-Path ([System.IO.Path]::GetTempPath()) ('Cyberbot-preflight-' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $stage | Out-Null
        $saved = @{}
        try {
            $archive = Join-Path $stage 'source.zip'
            $testRoot = Join-Path $stage 'source'
            & git archive --format=zip "--output=$archive" HEAD
            if ($LASTEXITCODE -ne 0) { throw 'Git source snapshot failed.' }
            Expand-Archive -LiteralPath $archive -DestinationPath $testRoot
            # Keep actual credentials, database paths and enabled provider flags out of test child.
            Get-ChildItem Env: | Where-Object { $_.Name -like 'CYBERBOT_*' -or $_.Name -in @('PYTHONPATH','PYTHONHOME') } | ForEach-Object {
                $saved[$_.Name] = $_.Value
                Remove-Item -LiteralPath ('Env:' + $_.Name)
            }
            Push-Location $testRoot
            try {
                & $python -m unittest discover -s tests -v
                if ($LASTEXITCODE -ne 0) { throw 'Isolated tests failed; do not start.' }
            } finally { Pop-Location }
        } finally {
            foreach ($name in $saved.Keys) { [Environment]::SetEnvironmentVariable($name,$saved[$name],'Process') }
            Remove-Item -LiteralPath $stage -Recurse -Force
        }
        Write-Host 'Local isolated unit tests passed. No provider or task started.'
    }
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Virtual environment missing. Use -Prepare explicitly.' }
    & $python -m tools.pilot_preflight
    if ($LASTEXITCODE -ne 0) { throw 'Preflight failed.' }
    Write-Host 'Report only: automatic entry and live execution remain unverified. No task started.'
} finally { Pop-Location }
