# Send sample OTLP traces/metrics/logs and verify ClickHouse received them.
# Requires dual collector running: .\scripts\run-collector-dual.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Read-Secret([string]$Name) {
    $path = Join-Path $Root $Name
    if (-not (Test-Path $path)) { return $null }
    return (Get-Content -Raw $path).Trim()
}

function Test-CollectorPort {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $c.Connect("127.0.0.1", 4318)
        $c.Close()
        return $true
    } catch {
        return $false
    }
}

if (-not (Test-CollectorPort)) {
    throw "Collector not listening on 127.0.0.1:4318. Start it first: .\scripts\run-collector-dual.ps1"
}

$now = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() * 1000000
$end = $now + 500000000
$traceId = -join ((1..32) | ForEach-Object { "{0:x}" -f (Get-Random -Maximum 16) })
$spanId = -join ((1..16) | ForEach-Object { "{0:x}" -f (Get-Random -Maximum 16) })
$service = "otel-sample-agent"
$spanName = "smoke.dual.test"

Write-Host "Sending OTLP trace to http://127.0.0.1:4318 ..."
$traceBody = @"
{
  "resourceSpans": [{
    "resource": {
      "attributes": [
        {"key": "service.name", "value": {"stringValue": "$service"}},
        {"key": "deployment.environment", "value": {"stringValue": "dev"}}
      ]
    },
    "scopeSpans": [{
      "scope": {"name": "smoke-test"},
      "spans": [{
        "traceId": "$traceId",
        "spanId": "$spanId",
        "name": "$spanName",
        "kind": 1,
        "startTimeUnixNano": "$now",
        "endTimeUnixNano": "$end",
        "status": {"code": 1}
      }]
    }]
  }]
}
"@
Invoke-RestMethod -Uri "http://127.0.0.1:4318/v1/traces" -Method Post `
    -ContentType "application/json" `
    -Body ([Text.Encoding]::UTF8.GetBytes($traceBody)) | Out-Null

Write-Host "Waiting 15s for batch export ..."
Start-Sleep -Seconds 15

$user = Read-Secret ".clickhouse_user"
$pw = Read-Secret ".clickhouse_password"
$ep = Read-Secret ".clickhouse_endpoint"
if (-not ($user -and $pw -and $ep)) {
    throw "Missing .clickhouse_* secret files in repo root"
}

$qCount = [uri]::EscapeDataString("SELECT count() FROM otel.otel_traces WHERE SpanName = '$spanName'")
$qLatest = [uri]::EscapeDataString("SELECT Timestamp, ServiceName, SpanName FROM otel.otel_traces ORDER BY Timestamp DESC LIMIT 3")

Write-Host ""
Write-Host "ClickHouse verification:"
$count = curl.exe -sS --ssl-no-revoke --http1.1 -u "${user}:${pw}" "${ep}/?query=${qCount}" --max-time 30
Write-Host "  Span '$spanName' count: $count"
Write-Host "  Latest traces:"
curl.exe -sS --ssl-no-revoke --http1.1 -u "${user}:${pw}" "${ep}/?query=${qLatest}" --max-time 30
Write-Host ""

if ([int]$count -ge 1) {
    Write-Host "PASS - ClickHouse received the smoke span."
    Write-Host "Check New Relic UI for service $service (wait 1-2 min)."
} else {
    Write-Host "FAIL - span not found in ClickHouse. Check collector logs in the other terminal."
    exit 1
}
