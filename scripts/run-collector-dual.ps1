# Dual export runner for Windows (PowerShell).
# Loads gitignored secret files and starts otelcol-contrib with dual config.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$ConfigRel = "collector\collector-config-dual.yaml"
$ConfigAbs = Join-Path $Root $ConfigRel
$BinCandidates = @(
    (Join-Path $Root "dist\otelcol-contrib\otelcol-contrib.exe"),
    (Join-Path $Root "dist\otel-custom\otel-custom.exe"),
    (Join-Path $Root "dist\otel-custom\otel-custom")
)

function Read-SecretFile([string]$Path) {
    if (-not (Test-Path $Path)) { return $null }
    return (Get-Content -Raw $Path).Trim()
}

# New Relic
if (-not $env:NEW_RELIC_LICENSE_KEY) {
    $env:NEW_RELIC_LICENSE_KEY = Read-SecretFile (Join-Path $Root ".new_relic_license_key")
}
if (-not $env:NEW_RELIC_LICENSE_KEY) {
    throw "Missing NEW_RELIC_LICENSE_KEY (set env or create .new_relic_license_key)"
}

# ClickHouse
if (-not $env:CLICKHOUSE_ENDPOINT) {
    $env:CLICKHOUSE_ENDPOINT = Read-SecretFile (Join-Path $Root ".clickhouse_endpoint")
}
if (-not $env:CLICKHOUSE_USER) {
    $env:CLICKHOUSE_USER = Read-SecretFile (Join-Path $Root ".clickhouse_user")
}
if (-not $env:CLICKHOUSE_PASSWORD) {
    $env:CLICKHOUSE_PASSWORD = Read-SecretFile (Join-Path $Root ".clickhouse_password")
}

$missing = @()
if (-not $env:CLICKHOUSE_ENDPOINT) { $missing += "CLICKHOUSE_ENDPOINT" }
if (-not $env:CLICKHOUSE_USER) { $missing += "CLICKHOUSE_USER" }
if (-not $env:CLICKHOUSE_PASSWORD) { $missing += "CLICKHOUSE_PASSWORD" }
if ($missing.Count -gt 0) {
    throw ("Missing ClickHouse settings: " + ($missing -join ", "))
}

if (-not (Test-Path $ConfigAbs)) {
    throw "Missing $ConfigRel - copy from collector-config-dual.yaml.example"
}

# Fail fast if another collector already owns :4318
try {
    $probe = New-Object System.Net.Sockets.TcpClient
    $probe.Connect("127.0.0.1", 4318)
    $probe.Close()
    Write-Host ""
    Write-Host "Port 4318 is already in use - collector may already be running."
    Write-Host "  Test now:  .\scripts\smoke-test-dual.ps1"
    Write-Host "  Send data: .\scripts\run-agent.ps1"
    Write-Host "  To restart: Get-Process otelcol-contrib | Stop-Process -Force"
    Write-Host ""
    exit 0
} catch {
    # port free - continue starting
}

$Bin = $BinCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Bin) {
    throw "No collector binary found under dist/. Download otelcol-contrib or build with ./scripts/build-collector.sh"
}

Write-Host ""
Write-Host "================================================================"
Write-Host "  Collector -> New Relic + ClickHouse"
Write-Host "================================================================"
Write-Host "  Binary: $Bin"
Write-Host "  Config: $ConfigRel"
Write-Host "  OTLP HTTP: http://127.0.0.1:4318"
Write-Host "  Press Ctrl+C to stop"
Write-Host "================================================================"
Write-Host ""

& $Bin --config=$ConfigAbs
