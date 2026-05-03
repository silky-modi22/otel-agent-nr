# otel-agent

Synthetic OpenTelemetry **traces**, **metrics**, and **logs** over **OTLP/HTTP**, plus a **custom OpenTelemetry Collector** built with [ocb](https://github.com/open-telemetry/opentelemetry-collector/blob/main/cmd/builder/README.md).

**New to OpenTelemetry?** Read **[docs/beginner-guide.md](docs/beginner-guide.md)** for a plain-language walkthrough: sample agent → collector → New Relic.

## Prerequisites

- Python 3.11+
- Docker (for `./scripts/build-collector.sh` on any OS, or for Compose)

## Quick start

One-time setup (from your clone of this repo, e.g. `~/extra/otel-agent`):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
./scripts/build-collector.sh
```

### Two terminals (recommended)

Open **two** terminal tabs in the **same directory** (your clone of this repo — **not** the literal path `/path/to/otel-agent`; use something like `~/extra/otel-agent`, or stay put if your prompt already ends with `otel-agent`).

Each helper script prints a **banner** so you can tell which role that window has. _(Reminder text like “wait for Everything is ready” belongs in your head, not pasted into the shell.)_

| Terminal | Command | What you’ll see |
|----------|---------|-----------------|
| **1 — Collector** | `./scripts/run-collector.sh` | Banner, then logs ending with **“Everything is ready”**. When Terminal 2 runs, **large blocks** of `ResourceLog` / `ResourceSpans` / `ResourceMetrics` (the **debug** exporter). |
| **2 — Sample agent** | `./scripts/run-agent.sh` | Banner, then usually **little output** while it sends OTLP to `localhost:4318` (defaults: 20s duration). |

Start **Terminal 1** first and wait for “Everything is ready”, then run **Terminal 2**.

Optional: `./scripts/run-agent.sh --duration 60 --interval 0.4`  

**New Relic:** create `collector/collector-config-nr.yaml` from [`collector/collector-config-nr.yaml.example`](collector/collector-config-nr.yaml.example), set `export NEW_RELIC_LICENSE_KEY="..."`, then Terminal 1: [`./scripts/run-collector-nr.sh`](scripts/run-collector-nr.sh), Terminal 2: `./scripts/run-agent.sh`. (NR config exports **only** to New Relic — no **`debug`** spam in Terminal 1; verify in the NR UI.)

### Same flow without helpers

```bash
./dist/otel-custom/otel-custom --config=collector/collector-config.yaml   # terminal 1
source .venv/bin/activate && python -m agent --duration 10 --interval 0.5   # terminal 2
```

### Send data to New Relic (short version)

1. `cp collector/collector-config-nr.yaml.example collector/collector-config-nr.yaml` and set **`otlphttp/newrelic`** **`endpoint`** if your NR region is not US (see [NR OTLP docs](https://docs.newrelic.com/docs/more-integrations/open-source-telemetry-integrations/opentelemetry/opentelemetry-setup/)).
2. `export NEW_RELIC_LICENSE_KEY="<your-ingest-license-key>"`
3. Terminal 1: `./scripts/run-collector-nr.sh`
4. Terminal 2: `./scripts/run-agent.sh --duration 30`

Details, regional endpoints, and verification: **[docs/beginner-guide.md](docs/beginner-guide.md)** (Phase B).

### Agent CLI

| Flag | Default | Purpose |
|------|---------|---------|
| `--endpoint` | `http://localhost:4318` | OTLP HTTP base URL |
| `--service-name` | `otel-sample-agent` | `service.name` |
| `--environment` | `dev` | `deployment.environment` |
| `--interval` | `1.0` | Seconds between synthetic requests |
| `--duration` | `0` | Stop after N seconds (`0` = until Ctrl+C) |
| `--error-rate` | `0.05` | Fraction of synthetic 5xx responses |
| `--metric-interval-ms` | `5000` | Metric export period |

Environment variables: `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME`, `DEPLOYMENT_ENVIRONMENT`.

## Custom collector build

[scripts/build-collector.sh](scripts/build-collector.sh) runs `ocb` inside `otel/opentelemetry-collector-builder:0.129.0`. It sets **GOOS/GOARCH** to match your machine so the binary runs locally (e.g. macOS arm64). Override with `GOOS=linux GOARCH=amd64` for a Linux server artifact.

Manifest: [collector/builder-config.yaml](collector/builder-config.yaml).

Full NR setup, endpoints by region, and troubleshooting: **[docs/beginner-guide.md](docs/beginner-guide.md)** · [New Relic OTLP docs](https://docs.newrelic.com/docs/more-integrations/open-source-telemetry-integrations/opentelemetry/opentelemetry-setup/).

## Docker

```bash
docker compose build collector
docker compose up collector
```

Run the agent on the host against `http://localhost:4318`.
