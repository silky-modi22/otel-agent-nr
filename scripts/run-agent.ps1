# Windows: run the sample OTLP agent (traces + metrics + logs).
# Uses uv (no system Python required). Start collector first.
# Usage: .\scripts\run-agent.ps1
#        .\scripts\run-agent.ps1 -Duration 30 -Interval 0.5
param(
    [double]$Duration = 20.0,
    [double]$Interval = 0.5
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Uv = @(
    "$env:USERPROFILE\.local\bin\uv.exe",
    "$env:LOCALAPPDATA\Programs\uv\uv.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $Uv) {
    throw "uv not found. Install from https://docs.astral.sh/uv/ or install Python 3.11+ and use: python -m agent --duration $Duration"
}

try {
    $c = New-Object System.Net.Sockets.TcpClient
    $c.Connect("127.0.0.1", 4318)
    $c.Close()
} catch {
    throw "Collector not on 127.0.0.1:4318. Start: .\scripts\run-collector-dual.ps1"
}

Write-Host ""
Write-Host "================================================================"
Write-Host "  Sample OTLP agent -> localhost:4318"
Write-Host "  Duration: ${Duration}s  Interval: ${Interval}s"
Write-Host "================================================================"
Write-Host ""

& $Uv run --with "opentelemetry-api>=1.27.0" `
    --with "opentelemetry-sdk>=1.27.0" `
    --with "opentelemetry-exporter-otlp-proto-http>=1.27.0" `
    -- python -m agent --duration $Duration --interval $Interval

Write-Host ""
Write-Host "Done. Verify:"
Write-Host "  ClickHouse: .\scripts\smoke-test-dual.ps1  (or SQL on otel.otel_traces)"
Write-Host "  New Relic: UI -> service otel-sample-agent"
