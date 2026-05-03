#!/usr/bin/env bash
# Terminal 1: collector with New Relic OTLP export.
# Requires: NEW_RELIC_LICENSE_KEY and collector/collector-config-nr.yaml (see example).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG_REL="collector/collector-config-nr.yaml"
CONFIG_ABS="$ROOT/$CONFIG_REL"

if [[ -z "${NEW_RELIC_LICENSE_KEY:-}" ]]; then
  echo "Missing NEW_RELIC_LICENSE_KEY."
  echo "Export your New Relic ingest license key in this shell, then retry:"
  echo "  export NEW_RELIC_LICENSE_KEY=\"<your-key>\""
  exit 1
fi

if [[ ! -f "$CONFIG_ABS" ]]; then
  echo "Missing $CONFIG_REL"
  echo "Create it from the template:"
  echo "  cp collector/collector-config-nr.yaml.example collector/collector-config-nr.yaml"
  echo "Edit otlphttp/newrelic endpoint if your NR region is not US."
  exit 1
fi

exec "$ROOT/scripts/run-collector.sh" "$CONFIG_REL"
