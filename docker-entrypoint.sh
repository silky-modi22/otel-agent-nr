#!/bin/sh
set -e

# Bind the FastAPI server to the platform-provided port on all interfaces.
export OTEL_AI_HTTP_HOST="0.0.0.0"
export OTEL_AI_HTTP_PORT="${PORT:-8000}"

# The GitHub poller and internal calls target the same in-container server.
export INTERNAL_INGEST_URL="http://127.0.0.1:${PORT:-8000}/ingest"

# The bundled collector listens on localhost:4318 inside this container.
export OTEL_EXPORTER_OTLP_ENDPOINT="${OTEL_EXPORTER_OTLP_ENDPOINT:-http://127.0.0.1:4318}"

# Don't block startup waiting for the collector; it's started from the dashboard.
export SKIP_COLLECTOR_CHECK="1"

# Materialize runtime collector configs from the committed .example templates.
for name in clickhouse dual nr; do
  src="collector/collector-config-${name}.yaml.example"
  dst="collector/collector-config-${name}.yaml"
  if [ -f "$src" ] && [ ! -f "$dst" ]; then
    cp "$src" "$dst"
  fi
done

exec python -m agent serve
