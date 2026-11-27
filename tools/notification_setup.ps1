param(
    [switch]$Install,
    [switch]$GenerateKeys,
    [ValidateRange(1,65535)][int]$Port
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$state = Join-Path $HOME '.cyberbot-private'
$venv = Join-Path $state 'notification-venv'
$py = Join-Path $venv 'Scripts\python.exe'
if (-not $Install) {
    Write-Host 'Preview only. Use -Install to prepare isolated notification environment.'
    Write-Host "State: $state"
    Write-Host 'No services, trading, push delivery or network exposure will be enabled.'
    return
}
New-Item -ItemType Directory -Path $state -Force | Out-Null
if (-not (Test-Path $py)) {
    & py -3.11 -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}
& $py -m pip install 'fastapi>=0.115,<1' 'pywebpush>=2,<3' 'cryptography>=43' 'tzdata' 'pytest>=8,<10' 'httpx>=0.27,<1'
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
$env:CYBERBOT_NOTIFICATION_STATE = $state
& $py -c 'import os; from pathlib import Path; from tools.notification_center import NotificationStore; from tools.notification_preferences import Preferences; from tools.notification_push_server import PushStore; from tools.notification_push_queue import PushQueue; p=Path(os.environ["CYBERBOT_NOTIFICATION_STATE"]); NotificationStore(p/"notifications.sqlite3"); Preferences(p/"preferences.sqlite3"); PushStore(p/"subscriptions.sqlite3"); PushQueue(p/"push-queue.sqlite3"); print("Notification databases initialized")'
if ($LASTEXITCODE -ne 0) { throw 'Database initialization failed.' }
if ($GenerateKeys) {
    & $py -m tools.notification_vapid_setup
    if ($LASTEXITCODE -ne 0) { throw 'VAPID provisioning failed; existing keys are preserved.' }
}
if ($Port) { & (Join-Path $PSScriptRoot 'notification_tailscale_check.ps1') -Port $Port }
Write-Host 'Preparation complete. API mounting, worker startup and phone verification remain manual.'
