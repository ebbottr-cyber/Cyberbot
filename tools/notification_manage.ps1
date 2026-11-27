param(
    [ValidateSet('Status','Install','Register','Start','Stop','Doctor')]
    [string]$Action = 'Status',
    [ValidateRange(1,65535)][int]$Port = 8000
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Push-Location $root
try {
    switch ($Action) {
        'Install' { & (Join-Path $PSScriptRoot 'notification_install.ps1') -Install }
        'Register' { & (Join-Path $PSScriptRoot 'notification_install.ps1') -Install -RegisterWorker }
        'Start' { & (Join-Path $PSScriptRoot 'notification_task.ps1') -Action Start }
        'Stop' { & (Join-Path $PSScriptRoot 'notification_task.ps1') -Action Stop }
        'Status' { & (Join-Path $PSScriptRoot 'notification_task.ps1') -Action Status }
        'Doctor' { & (Join-Path $PSScriptRoot 'notification_doctor.ps1') -Port $Port }
    }
} finally {
    Pop-Location
}
Write-Host 'Notification worker only. API server, HTTPS and live trading settings unchanged.'
