# Default: read-only preflight. -Prepare installs only project dependencies and runs isolated tests.
param([switch]$Prepare,[switch]$PreferPython311)
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
            $candidates = @()
            $launcher = Get-Command py.exe -CommandType Application -ErrorAction SilentlyContinue
            if ($launcher) {
                foreach ($v in $(if ($PreferPython311) { @('-3.11','-3.12') } else { @('-3.12','-3.11') })) {
                    $located = & $launcher.Source $v -c "import sys; print(sys.executable)" 2>$null
                    if ($LASTEXITCODE -eq 0 -and $located) { $candidates += [string]($located | Select-Object -Last 1) }
                }
            }
            foreach ($command in @(Get-Command python.exe,python3.exe -CommandType Application -All -ErrorAction SilentlyContinue)) {
                if ($command.Source -notlike '*\Microsoft\WindowsApps\*') { $candidates += $command.Source }
            }
            foreach ($version in $(if ($PreferPython311) { @('311','312') } else { @('312','311') })) {
                foreach ($folder in @("$env:LOCALAPPDATA\Programs\Python\Python$version", "$env:ProgramFiles\Python$version", "C:\Python$version")) {
                    $candidates += (Join-Path $folder 'python.exe')
                }
            }
            $basePython = $null
            foreach ($candidate in ($candidates | Select-Object -Unique)) {
                if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
                & $candidate -I -c "import sys, venv; assert sys.version_info[:2] in [(3,11),(3,12)]" 2>$null
                if ($LASTEXITCODE -eq 0) { $basePython = $candidate; break }
            }
            if (-not $basePython) { throw 'Python 3.11/3.12 not found. Install Python 3.12, reopen PowerShell and retry.' }
            & $basePython -I -m venv .venv
            if ($LASTEXITCODE -ne 0) { throw 'Python venv creation failed.' }
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
