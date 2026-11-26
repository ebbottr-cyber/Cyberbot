param(
    [string]$Source = "$HOME\EBBot-CanliTest\local\equity5m\piyasa_5m_research.sqlite3",
    [string]$Output = ""
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not $Output) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $Output = Join-Path $HOME "Cyberbot-Data\equity-intraday-$stamp.sqlite3"
}
if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
    throw "EBBot kaynak SQLite dosyasi bulunamadi: $Source"
}
$python = Join-Path $HOME "EBBot-CanliTest\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}
$script = Join-Path $root "tools\import_ebbot_5m.py"
if (-not (Test-Path -LiteralPath $script -PathType Leaf)) {
    throw "Aktarim araci bulunamadi. Dogru Cyberbot dalini kullanin."
}
& $python $script --source $Source --output $Output
if ($LASTEXITCODE -ne 0) { throw "Aktarim basarisiz. Kaynak korunuyor." }
Write-Host "VERI AKTARILDI: $Output"
Write-Host "GitHub'a otomatik yukleme veya emir gonderimi yapilmadi."
