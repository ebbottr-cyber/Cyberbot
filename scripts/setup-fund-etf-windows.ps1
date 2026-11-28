# Fund & ETF setup, isolated from existing market environments.
[CmdletBinding()]
param(
    [string]$PythonExecutable,
    [switch]$SkipBrowser,
    [switch]$CheckOnly
)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$venv=Join-Path $root 'var\fund-etf-venv'
$python=Join-Path $venv 'Scripts\python.exe'
$localConfig=Join-Path $root 'var\fund-etf-config.json'
$example=Join-Path $root 'config\fund-etf.example.json'
function Invoke-Checked {
    param([string]$Exe,[string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE): $Exe" }
}
Push-Location $root
try {
    foreach ($file in @('requirements.txt','requirements-fund-etf.txt','config\fund-etf.example.json','tools\fund_etf_worker.py','cyberbot\fund_etf_api.py')) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Fund ETF checkout missing: $file" }
    }
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        if ($CheckOnly) { throw 'Fund ETF environment missing.' }
        if (Test-Path -LiteralPath $venv) { throw 'Incomplete existing environment; inspect it manually. No files removed.' }
        New-Item -ItemType Directory -Path (Join-Path $root 'var') -Force | Out-Null
        if ($PythonExecutable) {
            Invoke-Checked $PythonExecutable @('-c','import sys; assert sys.version_info[:2] in [(3,11),(3,12)]')
            Invoke-Checked $PythonExecutable @('-m','venv',$venv)
        } elseif (Get-Command py -ErrorAction SilentlyContinue) {
            & py -3.12 -c "import sys"
            if ($LASTEXITCODE -eq 0) { Invoke-Checked 'py' @('-3.12','-m','venv',$venv) }
            else { Invoke-Checked 'py' @('-3.11','-m','venv',$venv) }
        } else {
            Invoke-Checked 'python' @('-c','import sys; assert sys.version_info[:2] in [(3,11),(3,12)]')
            Invoke-Checked 'python' @('-m','venv',$venv)
        }
    }
    Invoke-Checked $python @('-c','import sys; assert sys.version_info[:2] in [(3,11),(3,12)]')
    if (-not $CheckOnly) {
        Invoke-Checked $python @('-m','pip','install','--disable-pip-version-check','-r','requirements.txt','-r','requirements-fund-etf.txt')
    }
    Invoke-Checked $python @('-m','pip','check')
    Invoke-Checked $python @('-c','import numpy, scipy, sklearn, lightgbm, xgboost, river, yfinance, httpx, fastapi; from google import genai; from zoneinfo import ZoneInfo; ZoneInfo("Europe/Istanbul"); import tools.fund_etf_cycle')
    if (-not (Test-Path -LiteralPath $localConfig)) {
        if ($CheckOnly) { throw 'Local configuration missing.' }
        # FileMode.CreateNew rejects races and never overwrites an existing config.
        $stream=[System.IO.File]::Open($localConfig,[System.IO.FileMode]::CreateNew)
        try {
            $bytes=[System.IO.File]::ReadAllBytes($example)
            $stream.Write($bytes,0,$bytes.Length)
        } finally { $stream.Dispose() }
    }
    Invoke-Checked $python @('-c','import json,sys; c=json.load(open(sys.argv[1],encoding="utf-8-sig")); assert isinstance(c,dict)', $localConfig)
    Invoke-Checked $python @('-m','unittest','discover','-s','tests','-p','test_fund_etf*.py','-v')
    if (-not $SkipBrowser) {
        $oldBrowser=$env:PLAYWRIGHT_BROWSERS_PATH
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH=Join-Path $root 'var\fund-etf-browsers'
            if (-not $CheckOnly) {
                Invoke-Checked $python @('-m','pip','install','--disable-pip-version-check','playwright>=1.50,<2')
                Invoke-Checked $python @('-m','playwright','install','chromium')
            }
            Invoke-Checked $python @('-m','tools.fund_etf_browser_smoke')
        } finally { $env:PLAYWRIGHT_BROWSERS_PATH=$oldBrowser }
    }
    Write-Host 'Fund ETF local setup checks passed. No worker or live provider started.'
    Write-Host 'Review var\fund-etf-config.json before running scripts\fund-etf-windows.ps1 -Mode Once.'
} finally { Pop-Location }
