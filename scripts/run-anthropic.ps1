# Windows: run a real Anthropic (Claude) call instrumented with OpenTelemetry.
# Sends GenAI traces + metrics over OTLP/HTTP to the collector on :4318.
# Start the collector first (dual = New Relic + ClickHouse):
#   .\scripts\run-collector-dual.ps1
# Usage: .\scripts\run-anthropic.ps1
#        .\scripts\run-anthropic.ps1 -Model "claude-3-5-sonnet-latest" -Prompt "Say hi"
param(
    [string]$Model = "claude-3-5-haiku-latest",
    [string]$Prompt = "Reply in one short sentence: what is OpenTelemetry used for?"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Read-SecretFile([string]$Path) {
    if (-not (Test-Path $Path)) { return $null }
    return (Get-Content -Raw $Path).Trim()
}

# Anthropic API key: env or gitignored .anthropic_api_key file
if (-not $env:ANTHROPIC_API_KEY) {
    $env:ANTHROPIC_API_KEY = Read-SecretFile (Join-Path $Root ".anthropic_api_key")
}
if (-not $env:ANTHROPIC_API_KEY) {
    throw "Missing ANTHROPIC_API_KEY (set env or create .anthropic_api_key)"
}

$Uv = @(
    "$env:USERPROFILE\.local\bin\uv.exe",
    "$env:LOCALAPPDATA\Programs\uv\uv.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $Uv) {
    throw "uv not found. Install from https://docs.astral.sh/uv/ or install Python 3.11+ and: pip install -r examples\anthropic_otel\requirements.txt; python examples\anthropic_otel\client.py"
}

# Collector must be listening on :4318
try {
    $c = New-Object System.Net.Sockets.TcpClient
    $c.Connect("127.0.0.1", 4318)
    $c.Close()
} catch {
    throw "Collector not on 127.0.0.1:4318. Start: .\scripts\run-collector-dual.ps1"
}

if (-not $env:OTEL_EXPORTER_OTLP_ENDPOINT) {
    $env:OTEL_EXPORTER_OTLP_ENDPOINT = "http://localhost:4318"
}
if (-not $env:OTEL_SERVICE_NAME) {
    $env:OTEL_SERVICE_NAME = "anthropic-otel-example"
}
$env:ANTHROPIC_EXAMPLE_MODEL = $Model
$env:ANTHROPIC_EXAMPLE_PROMPT = $Prompt

Write-Host ""
Write-Host "================================================================"
Write-Host "  Anthropic (Claude) -> OpenTelemetry -> localhost:4318"
Write-Host "  Model:   $Model"
Write-Host "  Service: $($env:OTEL_SERVICE_NAME)"
Write-Host "================================================================"
Write-Host ""

& $Uv run --with "anthropic>=0.40.0,<1" `
    --with "truststore>=0.9.0" `
    --with "opentelemetry-api>=1.38.0,<2" `
    --with "opentelemetry-sdk>=1.38.0,<2" `
    --with "opentelemetry-exporter-otlp-proto-http>=1.38.0,<2" `
    --with "opentelemetry-instrumentation-anthropic>=0.62.0,<1" `
    -- python examples\anthropic_otel\client.py

Write-Host ""
Write-Host "Done. Verify:"
Write-Host "  ClickHouse: SELECT count() FROM otel.otel_traces WHERE ServiceName = 'anthropic-otel-example'"
Write-Host "  New Relic:  UI -> service anthropic-otel-example"
