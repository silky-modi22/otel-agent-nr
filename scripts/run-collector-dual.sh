#!/usr/bin/env bash
# Terminal 1: collector with dual export → New Relic + ClickHouse.
# Requires: NEW_RELIC_LICENSE_KEY, CLICKHOUSE_* env (or secret files), and
# collector/collector-config-dual.yaml (see example).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG_REL="collector/collector-config-dual.yaml"
CONFIG_ABS="$ROOT/$CONFIG_REL"

# --- New Relic ---
if [[ -z "${NEW_RELIC_LICENSE_KEY:-}" ]]; then
  _key_file="${NEW_RELIC_LICENSE_KEY_FILE:-$ROOT/.new_relic_license_key}"
  if [[ -f "$_key_file" ]]; then
    NEW_RELIC_LICENSE_KEY="$(tr -d '[:space:]' < "$_key_file")"
    export NEW_RELIC_LICENSE_KEY
  fi
fi

if [[ -z "${NEW_RELIC_LICENSE_KEY:-}" ]]; then
  echo "Missing NEW_RELIC_LICENSE_KEY."
  echo "  export NEW_RELIC_LICENSE_KEY=\"<your-ingest-key>\""
  echo "  echo '<your-ingest-key>' > .new_relic_license_key"
  exit 1
fi

# --- ClickHouse ---
if [[ -z "${CLICKHOUSE_ENDPOINT:-}" && -f "$ROOT/.clickhouse_endpoint" ]]; then
  CLICKHOUSE_ENDPOINT="$(tr -d '[:space:]' < "$ROOT/.clickhouse_endpoint")"
  export CLICKHOUSE_ENDPOINT
fi
if [[ -z "${CLICKHOUSE_USER:-}" && -f "$ROOT/.clickhouse_user" ]]; then
  CLICKHOUSE_USER="$(tr -d '[:space:]' < "$ROOT/.clickhouse_user")"
  export CLICKHOUSE_USER
fi
if [[ -z "${CLICKHOUSE_PASSWORD:-}" ]]; then
  _ch_pw_file="${CLICKHOUSE_PASSWORD_FILE:-$ROOT/.clickhouse_password}"
  if [[ -f "$_ch_pw_file" ]]; then
    CLICKHOUSE_PASSWORD="$(tr -d '\r\n' < "$_ch_pw_file")"
    export CLICKHOUSE_PASSWORD
  fi
fi

missing=0
if [[ -z "${CLICKHOUSE_ENDPOINT:-}" ]]; then
  echo "Missing CLICKHOUSE_ENDPOINT (e.g. https://HOST:8443)."
  missing=1
fi
if [[ -z "${CLICKHOUSE_USER:-}" ]]; then
  echo "Missing CLICKHOUSE_USER (usually default)."
  missing=1
fi
if [[ -z "${CLICKHOUSE_PASSWORD:-}" ]]; then
  echo "Missing CLICKHOUSE_PASSWORD."
  echo "  export CLICKHOUSE_PASSWORD='...'"
  echo "  echo '...' > .clickhouse_password"
  missing=1
fi
if [[ "$missing" -eq 1 ]]; then
  echo "See docs/clickhouse-collector-checklist.md"
  exit 1
fi

if [[ ! -f "$CONFIG_ABS" ]]; then
  echo "Missing $CONFIG_REL"
  echo "Create it from the template:"
  echo "  cp collector/collector-config-dual.yaml.example collector/collector-config-dual.yaml"
  exit 1
fi

exec "$ROOT/scripts/run-collector.sh" "$CONFIG_REL"
