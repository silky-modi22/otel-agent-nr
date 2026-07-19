# Real Gemini traffic -> OpenTelemetry -> Collector -> New Relic + ClickHouse

This example runs **one real** Google Gemini `generate_content` call instrumented with the
**official** OpenTelemetry GenAI instrumentation **`opentelemetry-instrumentation-google-genai`**
so spans and metrics follow **gen_ai.\*** semantic conventions, then exports **OTLP/HTTP** to the
same collector the rest of this repo uses (default `http://localhost:4318`). The dual collector
config forwards that data to **both New Relic and ClickHouse**.

It is the Gemini counterpart of [`examples/anthropic_otel/`](../anthropic_otel/README.md) and
[`examples/openai_otel/`](../openai_otel/README.md).

> **SDK note:** this example uses the **modern** `google-genai` SDK (import `google.genai`, the
> same SDK `python -m agent serve` uses) together with the official
> `opentelemetry-instrumentation-google-genai` instrumentation. It replaces the previously used
> deprecated Traceloop `opentelemetry-instrumentation-google-generativeai` + classic
> `google-generativeai` SDK, which had stopped emitting spans.
>
> For robustness the client **also** wraps the call in an explicit manual span
> (`gemini.generate_content`) with model/latency/token attributes, so at least one trace row
> lands even if auto-instrumentation emits nothing.

## Prerequisites

- Python 3.11+ (or `uv`, used by the PowerShell runner)
- **Gemini API key**: `GEMINI_API_KEY` (or `GOOGLE_API_KEY` as a fallback)
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
$env:GEMINI_API_KEY = "AIza..."   # or create a gitignored .gemini_api_key file
.\scripts\run-gemini.ps1
# optional: .\scripts\run-gemini.ps1 -Model "gemini-1.5-flash" -Prompt "Say hello in 5 words."
```

**Linux/macOS / manual:**

```bash
python3 -m venv examples/gemini_otel/.venv
source examples/gemini_otel/.venv/bin/activate
pip install -r examples/gemini_otel/requirements.txt

export GEMINI_API_KEY="AIza..."               # required (or GOOGLE_API_KEY)
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4318"
export OTEL_SERVICE_NAME="gemini-otel-example"
# optional: export GEMINI_EXAMPLE_MODEL="gemini-2.5-flash"
# optional: export GEMINI_EXAMPLE_PROMPT="Say hello in 5 words."

python examples/gemini_otel/client.py
```

You should see a short Gemini reply and a message that OTLP was flushed.

## Step 3 - Verify

### ClickHouse

The exporter creates database `otel` and `otel_*` tables (`create_schema: true`).

```sql
SHOW TABLES FROM otel;

SELECT Timestamp, ServiceName, SpanName
FROM otel.otel_traces
WHERE ServiceName = 'gemini-otel-example'
ORDER BY Timestamp DESC
LIMIT 20;
```

On Windows you can also run `.\scripts\smoke-test-dual.ps1`.

### New Relic

Open the **`gemini-otel-example`** entity under OpenTelemetry / distributed tracing.
Allow **1-2 minutes** for data to appear.

## Client flags / env vars

| Env var                     | Default                     | Purpose                          |
| --------------------------- | --------------------------- | -------------------------------- |
| `GEMINI_API_KEY`            | (required)                  | Gemini API key                   |
| `GOOGLE_API_KEY`            | (fallback)                  | Used if `GEMINI_API_KEY` unset   |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4318`   | OTLP HTTP base URL               |
| `OTEL_SERVICE_NAME`         | `gemini-otel-example`       | `service.name`                   |
| `DEPLOYMENT_ENVIRONMENT`    | `dev`                       | `deployment.environment`         |
| `GEMINI_EXAMPLE_MODEL`      | `gemini-2.5-flash`          | Gemini model id                  |
| `GEMINI_EXAMPLE_PROMPT`     | (short OTel question)        | Prompt text                      |
| `GEMINI_TRACE_CONTENT`      | `false`                     | Capture prompts/completions      |

## Privacy and message content

**By default this example sets `GEMINI_TRACE_CONTENT=false`** (mapped to the instrumentation's
`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=NO_CONTENT`) so the Google GenAI
instrumentation does **not** record prompts and completions to span attributes.
Set `GEMINI_TRACE_CONTENT=true` (mapped to `SPAN_ONLY`) to capture them - they will then flow to
the collector, **New Relic**, and **ClickHouse** under your retention policy and may contain PII
(see the [package docs](https://pypi.org/project/opentelemetry-instrumentation-google-genai/)).
