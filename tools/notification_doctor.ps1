param(
    [ValidateRange(1,65535)][int]$Port = 8000
)
$ErrorActionPreference = 'Stop'
$state = Join-Path $HOME '.cyberbot-private'
$base = "http://127.0.0.1:$Port"
$results = @()
foreach ($path in @('/','/manifest.webmanifest','/sw.js','/pwa/version','/api/notifications','/api/notifications/health','/api/research-news')) {
    try {
        $r = Invoke-WebRequest -Uri ($base + $path) -UseBasicParsing -TimeoutSec 5 -MaximumRedirection 0
        $results += [pscustomobject]@{Check=$path; Status=[int]$r.StatusCode; Detail='HTTP response'}
    } catch {
        $status = 'Unavailable'
        if ($_.Exception.Response) { $status = [int]$_.Exception.Response.StatusCode }
        $results += [pscustomobject]@{Check=$path; Status=$status; Detail='Check server, feature flag or access policy'}
    }
}
$results | Format-Table -AutoSize
$task = Get-ScheduledTask -TaskName 'Cyberbot-NotificationWorker' -TaskPath '\' -ErrorAction SilentlyContinue
if ($task) { $task | Select-Object TaskName,State } else { Write-Host 'Notification task not registered.' }
foreach ($name in @('notifications.sqlite3','preferences.sqlite3','subscriptions.sqlite3','push-queue.sqlite3','research-news.sqlite3','notification-health.json')) {
    $file = Join-Path $state $name
    [pscustomobject]@{File=$name; Exists=(Test-Path -LiteralPath $file)}
}
$health = Join-Path $state 'notification-health.json'
if (Test-Path -LiteralPath $health) {
    try {
        $data = Get-Content -LiteralPath $health -Raw | ConvertFrom-Json
        $age = ([DateTimeOffset]::UtcNow - [DateTimeOffset]::Parse($data.finished_at)).TotalSeconds
        Write-Host ("Worker status: " + $data.status + "; age seconds: " + [math]::Round($age))
        if ($age -gt 900 -or $age -lt 0) { Write-Warning 'Worker heartbeat stale or invalid.' }
    } catch { Write-Warning 'Worker health record could not be parsed.' }
}
Write-Host 'Read-only diagnostics. Tailscale-only mode can reject loopback HTTP by design.'
Write-Host 'HTTP success does not verify phone delivery or trading readiness.'
