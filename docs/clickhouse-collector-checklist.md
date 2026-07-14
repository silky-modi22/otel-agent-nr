# ClickHouse + New Relic dual collector checklist

Use this to run the **custom collector** with **dual export**: OTLP → **New Relic** and **ClickHouse**.

## Architecture

```text
Python agent / OpenAI example / AI ingest
  → OTLP/HTTP :4318
  → otel-custom collector (batch)
      → New Relic (otlphttp)
      → ClickHouse (otel database / otel_* tables)
```

## 1. Rebuild the collector (required once after adding ClickHouse)

The ClickHouse exporter is a **contrib** component. Rebuild so `otel-custom` includes it:

```bash
./scripts/build-collector.sh
```

Requires Docker. Produces `dist/otel-custom/otel-custom`.

## 2. Config file (local only; gitignored)

```bash
cp collector/collector-config-dual.yaml.example collector/collector-config-dual.yaml
```

Edit `otlphttp/newrelic.endpoint` if your New Relic region is not US (EU: `https://otlp.eu01.nr-data.net`).

## 3. Credentials

### New Relic

```bash
export NEW_RELIC_LICENSE_KEY="<ingest-license-key>"
# or: echo '<key>' > .new_relic_license_key
```

### ClickHouse Cloud (Connect → HTTPS)

```bash
export CLICKHOUSE_ENDPOINT="https://<your-host>.azure.clickhouse.cloud:8443"
export CLICKHOUSE_USER="default"
export CLICKHOUSE_PASSWORD="<db-password>"
```

Optional one-line files (gitignored):

- `.clickhouse_endpoint`
- `.clickhouse_user`
- `.clickhouse_password`

For the **dashboard UI** (`python -m agent serve`):

1. Open `http://127.0.0.1:8000/`
2. Click **Run GitHub to ClickHouse test** (starts collector if needed, polls GitHub once, queries ClickHouse)
3. Or manually: **ClickHouse** or **NR + ClickHouse** collector, then **Start GitHub poll**
4. Open the **ClickHouse** tab and click **Refresh**

Requires: `.clickhouse_*` files, `GEMINI_API_KEY`, optional `.github_token`, and `otelcol-contrib` or rebuilt `otel-custom` under `dist/`.

## 4. Start dual collector

Linux/macOS (custom binary after rebuild):

```bash
./scripts/run-collector-dual.sh
```

Windows (PowerShell — uses `dist/otelcol-contrib/otelcol-contrib.exe`):

```powershell
.\scripts\run-collector-dual.ps1
```

Wait for **Everything is ready**. OTLP HTTP listens on **4318**.

If ClickHouse export fails on Windows with TLS / “connection forcibly closed”, the dual example config already sets `compress: none`, `async_insert: false`, and `tls.insecure_skip_verify: true` for corporate TLS proxies.

## 5. Send sample data

```bash
./scripts/run-agent.sh --duration 30
```

## 6. Verify

### New Relic

UI → APM / OpenTelemetry for `service.name` (e.g. `otel-sample-agent`). Allow 1–2 minutes.

### ClickHouse

The exporter creates database `otel` and tables such as `otel_traces`, `otel_logs`, `otel_metrics_*` when `create_schema: true`.

```sql
SHOW TABLES FROM otel;

SELECT count() FROM otel.otel_traces;
SELECT Timestamp, ServiceName, SpanName
FROM otel.otel_traces
ORDER BY Timestamp DESC
LIMIT 20;
```

With ClickHouse MCP configured in Cursor, ask the agent to run those queries.

## Troubleshooting

| Symptom | Likely cause |
|--------|----------------|
| Collector binary lacks `clickhouse` exporter | Rebuild with `./scripts/build-collector.sh` |
| Auth / TLS errors to ClickHouse | Wrong host/port; use `https://HOST:8443` from Cloud Connect |
| Missing env at startup | `CLICKHOUSE_ENDPOINT` / `USER` / `PASSWORD` not set in that shell |
| NR **403** | Wrong NR region endpoint or wrong key type |
| Empty ClickHouse tables | Agent not sending, or exporter errors in collector logs |

Related: [nr-collector-checklist.md](nr-collector-checklist.md) · [beginner-guide.md](beginner-guide.md)
