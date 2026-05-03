#!/usr/bin/env bash
# Run in **Terminal 1** and leave it open. Shows OTLP receive + debug output.
# Usage: ./scripts/run-collector.sh [path/to/config.yaml]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
BIN="$ROOT/dist/otel-custom/otel-custom"
CONFIG="${1:-collector/collector-config.yaml}"
if [[ ! -x "$BIN" ]]; then
  echo "Missing executable: $BIN"
  echo "Build it first:  ./scripts/build-collector.sh"
  exit 1
fi
if [[ ! -f "$CONFIG" ]]; then
  echo "Config not found: $CONFIG"
  exit 1
fi

cat << EOF

================================================================
  TERMINAL 1 — OpenTelemetry Collector (this window)
================================================================
  Role: Receives OTLP on your machine
  - HTTP  : http://0.0.0.0:4318  (default config: HTTP only; same as the sample agent)
  - gRPC  is off in the default yaml so another app can use :4317 without conflict.

  What you should see after start:
  - A line containing: "Everything is ready. Begin running and processing data."
  - After you start the sample agent in Terminal 2, large blocks of text
    (ResourceLog, ResourceSpans, ResourceMetrics) = data is flowing.

  Config: $CONFIG
  Press Ctrl+C here to stop the collector.
================================================================

EOF

exec "$BIN" --config="$CONFIG"
