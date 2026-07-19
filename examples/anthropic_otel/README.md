# Real Anthropic traffic -> OpenTelemetry -> Collector -> New Relic + ClickHouse

This example runs **one real** Anthropic `messages.create` (Claude) call instrumented with
**`opentelemetry-instrumentation-anthropic`** (Traceloop) so spans and metrics follow
**Gen AI** conventions, then exports **OTLP/HTTP** to the same collector the rest of this
repo uses (default `http://localhost:4318`). The dual collector config forwards that data to
**both New Relic and ClickHouse**.

It is the Anthropic counterpart of [`examples/openai_otel/`](../openai_otel/README.md).

## Prerequisites

- Python 3.11+ (or `uv`, used by the PowerShell runner)
- **Anthropic API key**: `ANTHROPIC_API_KEY`
- Collector running with the **dual** (New Relic + ClickHouse) config
- New Relic ingest key + ClickHouse credentials (already configured if you use the `.new_relic_license_key` / `.clickhouse_*` secret files)

## Step 1 - Dual collector (Terminal 1)

Follow [docs/clickhouse-collector-checklist.md](../../docs/clickhouse-collector-checklist.md). In short:

1. `cp collector/collector-config-dual.yaml.example collector/collector-config-dual.yaml` (already present in this repo)
2. Set credentials via env or gitignored secret files:
   - `NEW_RELIC_LICENSE_KEY` (or `.new_relic_license_key`)
   - `CLICKHOUSE_ENDPOINT` / `CLICKHOUSE_USER` / `CLICKHOUSE_PASSWORD` (or `.clickhouse_endpoint` / `.clickhouse_user` / `.clickhouse_password`)
3. Start the collector and wait for **Everything is ready** (OTLP on **4318**):

**Windows (PowerShell):**

```powershell
.\scripts\run-collector-dual.ps1
```

**Linux/macOS:**

```bash
./scripts/run-collector-dual.sh
```

For **ClickHouse only** (no New Relic), use `collector/collector-config-clickhouse.yaml` with
`./scripts/run-collector.sh collector/collector-config-clickhouse.yaml` instead - the client below is unchanged.

## Step 2 - Run the client (Terminal 2)

**Windows (PowerShell)** - `uv` handles the dependencies, no manual venv needed:

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."   # or create a gitignored .anthropic_api_key file
.\scripts\run-anthropic.ps1
# optional: .\scripts\run-anthropic.ps1 -Model "claude-3-5-sonnet-latest" -Prompt "Say hello in 5 words."
```

**Linux/macOS / manual:**

```bash
python3 -m venv examples/anthropic_otel/.venv
source examples/anthropic_otel/.venv/bin/activate
pip install -r examples/anthropic_otel/requirements.txt

export ANTHROPIC_API_KEY="sk-ant-..."          # required
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4318"
export OTEL_SERVICE_NAME="anthropic-otel-example"
# optional: export ANTHROPIC_EXAMPLE_MODEL="claude-3-5-haiku-latest"
# optional: export ANTHROPIC_EXAMPLE_PROMPT="Say hello in 5 words."

python examples/anthropic_otel/client.py
```

You should see a short Claude reply and a message that OTLP was flushed.

## Step 3 - Verify

### ClickHouse

The exporter creates database `otel` and `otel_*` tables (`create_schema: true`).

```sql
SHOW TABLES FROM otel;

SELECT Timestamp, ServiceName, SpanName
FROM otel.otel_traces
WHERE ServiceName = 'anthropic-otel-example'
ORDER BY Timestamp DESC
LIMIT 20;
```

On Windows you can also run `.\scripts\smoke-test-dual.ps1`.

### New Relic

Open the **`anthropic-otel-example`** entity under OpenTelemetry / distributed tracing.
Allow **1-2 minutes** for data to appear.

## Client flags / env vars

| Env var                     | Default                     | Purpose                          |
| --------------------------- | --------------------------- | -------------------------------- |
| `ANTHROPIC_API_KEY`         | (required)                  | Anthropic API key                |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4318`   | OTLP HTTP base URL               |
| `OTEL_SERVICE_NAME`         | `anthropic-otel-example`    | `service.name`                   |
| `DEPLOYMENT_ENVIRONMENT`    | `dev`                       | `deployment.environment`         |
| `ANTHROPIC_EXAMPLE_MODEL`   | `claude-3-5-haiku-latest`   | Claude model id                  |
| `ANTHROPIC_EXAMPLE_PROMPT`  | (short OTel question)        | Prompt text                      |

## Privacy and message content

**By default the Traceloop Anthropic instrumentation records prompts and completions**
to span attributes, which then flow to the collector, **New Relic**, and **ClickHouse**
under your retention policy. These may contain PII. Disable content capture if you do not
intend to store prompts/responses - set `TRACELOOP_TRACE_CONTENT=false` (see the
[package docs](https://pypi.org/project/opentelemetry-instrumentation-anthropic/)).
