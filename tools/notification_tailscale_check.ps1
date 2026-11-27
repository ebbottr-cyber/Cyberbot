param(
    [Parameter(Mandatory=$true)]
    [ValidateRange(1,65535)][int]$Port
)
$ErrorActionPreference = 'Stop'
$ts = Get-Command tailscale -ErrorAction SilentlyContinue
if (-not $ts) { throw 'Tailscale CLI bulunamadi.' }
$raw = & $ts.Source status --json
if ($LASTEXITCODE -ne 0) { throw 'Tailscale durum bilgisi alinamadi.' }
$status = ($raw -join "`n") | ConvertFrom-Json
$dns = [string]$status.Self.DNSName
$dns = $dns.TrimEnd('.')
$local = Test-NetConnection -ComputerName 127.0.0.1 -Port $Port -InformationLevel Quiet -WarningAction SilentlyContinue
$https = $false
if ($status.BackendState -eq 'Running' -and $dns -match '^[a-zA-Z0-9.-]+\.ts\.net$') {
    try {
        $r = Invoke-WebRequest -Uri "https://$dns/" -Method Head -TimeoutSec 10 -MaximumRedirection 0 -UseBasicParsing
        $https = ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300)
    } catch { $https = $false }
}
[pscustomobject]@{
    tailscale_running = ($status.BackendState -eq 'Running')
    local_port = $Port
    local_tcp_reachable = [bool]$local
    pwa_candidate_url = $(if ($dns -match '^[a-zA-Z0-9.-]+\.ts\.net$') {"https://$dns/"} else {$null})
    https_head_success = $https
    serve_configuration_changed = $false
    phone_push_verified = $false
} | ConvertTo-Json
# Inspect existing Serve/Funnel configuration without changing it.
& $ts.Source serve status
& $ts.Source funnel status
