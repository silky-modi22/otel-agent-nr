# Windows: run AI ingest server + dashboard (Gemini + /ingest + UI).
# Uses uv from ~/.local/bin when uv is not on PATH.
# Usage: .\scripts\run-serve.ps1
#        .\scripts\run-serve.ps1 -HttpPort 8000
param(
    [int]$HttpPort = 8000
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Find-Uv {
    $candidates = @(
        "$env:USERPROFILE\.local\bin\uv.exe",
        "$env:LOCALAPPDATA\Programs\uv\uv.exe"
    )
    foreach ($path in $candidates) {
        if (Test-Path $path) { return $path }
    }
    $onPath = Get-Command uv -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    return $null
}

$Uv = Find-Uv
if (-not $Uv) {
    throw @"
uv not found. Install it, then retry:
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
Or use full path:
  & `"$env:USERPROFILE\.local\bin\uv.exe`" run ...
"@
}

# Port check
try {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $HttpPort)
    $listener.Start()
    $listener.Stop()
} catch {
    throw "Port $HttpPort is already in use. Stop the other server or use: .\scripts\run-serve.ps1 -HttpPort 8001"
}

Write-Host ""
Write-Host "================================================================"
Write-Host "  AI ingest server + dashboard"
Write-Host "  Dashboard: http://127.0.0.1:${HttpPort}/"
Write-Host "  uv: $Uv"
Write-Host "  Keys: .gemini_api_key or GEMINI_API_KEY"
Write-Host "================================================================"
Write-Host ""

& $Uv run `
    --with "opentelemetry-api>=1.27.0,<2" `
    --with "opentelemetry-sdk>=1.27.0,<2" `
    --with "opentelemetry-exporter-otlp-proto-http>=1.27.0,<2" `
    --with "google-genai>=1.0.0,<2" `
    --with "fastapi>=0.115.0,<1" `
    --with "uvicorn[standard]>=0.32.0,<1" `
    --with "pydantic>=2.9.0,<3" `
    -- python -m agent serve `
        --http-port $HttpPort `
        --otel-endpoint "http://localhost:4318"
