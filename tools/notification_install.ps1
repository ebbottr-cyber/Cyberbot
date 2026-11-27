param(
    [switch]$Install,
    [switch]$RegisterWorker,
    [switch]$StartWorker
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
if (-not $Install) {
    Write-Host 'Onizleme: -Install ile izole kurulum ve cevrimdisi testler.'
    Write-Host 'Istege bagli: -RegisterWorker ve -StartWorker.'
    return
}
if ($StartWorker -and -not $RegisterWorker) {
    throw 'StartWorker requires RegisterWorker.'
}
Push-Location $root
try {
    & (Join-Path $PSScriptRoot 'notification_setup.ps1') -Install
    $python = Join-Path $HOME '.cyberbot-private\notification-venv\Scripts\python.exe'
    & $python -m pytest -q (Get-ChildItem 'tests/test_notification_*.py' | ForEach-Object { $_.FullName })
    if ($LASTEXITCODE -ne 0) { throw 'Notification tests failed. Worker not registered or started.' }
    if ($RegisterWorker) {
        $task = Get-ScheduledTask -TaskName 'Cyberbot-NotificationWorker' -TaskPath '\' -ErrorAction SilentlyContinue
        if ($task) { throw 'Existing worker task preserved. Review it before starting.' }
        & (Join-Path $PSScriptRoot 'notification_task.ps1') -Action Register
        if ($StartWorker) {
            & (Join-Path $PSScriptRoot 'notification_task.ps1') -Action Start
        }
    }
    Write-Host 'Notification preparation and offline tests completed.'
    Write-Host 'Existing API process unchanged. Panel activation, HTTPS, VAPID and phone verification remain separate.'
    Write-Host 'No live trading, push delivery or network exposure enabled.'
} finally {
    Pop-Location
}
