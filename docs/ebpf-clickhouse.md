# eBPF telemetry to ClickHouse (Grafana Beyla)

This sends **eBPF-generated** telemetry to ClickHouse with **zero code changes** to
the instrumented app. [Grafana Beyla](https://grafana.com/docs/beyla/latest/)
uses eBPF to watch a process at the kernel level and emit OpenTelemetry
traces + metrics, which the custom collector then writes to ClickHouse Cloud.

```
app  ──(eBPF, Beyla)──▶  OTel collector (clickhouse exporter)  ──▶  ClickHouse Cloud
                                                                     otel.otel_traces
                                                                     otel.otel_metrics_*
```

## Why not Windows or Railway?

eBPF runs **inside the Linux kernel** and needs elevated privileges
(`CAP_BPF` / `CAP_SYS_ADMIN`, access to `/sys/kernel/debug`, a BTF-enabled
kernel). Because of that it **cannot** run:

- on **Windows** directly (no Linux kernel), or
- on the **Railway** deployment (managed containers are not privileged and have
  no host-kernel access).

So the eBPF pipeline runs locally on a **privileged Linux host**. The easiest
option on a Windows machine is **WSL2**, which ships a real Linux kernel with
eBPF/BTF enabled.

## Prerequisites (WSL2 on Windows)

1. **Install WSL2** (PowerShell as Administrator, then reboot):

   ```powershell
   wsl --install
   wsl --update
   ```

2. **Install Docker inside WSL2** (either Docker Desktop with the WSL2 backend
   enabled, or Docker Engine installed directly in the Ubuntu distro).

3. **Confirm the kernel has BTF** (from a WSL2 terminal) — this file must exist:

   ```bash
   ls /sys/kernel/btf/vmlinux
   ```

   WSL2 kernels 5.10+ have this. If missing, run `wsl --update`.

## Setup

From a **WSL2 / Linux** terminal, in the repo root:

1. Create your env file with ClickHouse credentials:

   ```bash
   cp .env.ebpf.example .env.ebpf
   # edit .env.ebpf and set CLICKHOUSE_ENDPOINT / USER / PASSWORD
   ```

2. Start the pipeline (builds the app + collector images on first run):

   ```bash
   docker compose -f docker-compose.ebpf.yml --env-file .env.ebpf up --build
   ```

   You should see three containers start: `app`, `beyla`, `collector`. Beyla
   logs `found process` / `instrumenting` lines once it attaches to the app.

## Generate traffic and verify

From another WSL2 terminal, hit the app a few times so Beyla captures requests:

```bash
for i in $(seq 1 20); do curl -s http://localhost:8000/health > /dev/null; done
```

Then query ClickHouse (Cloud SQL console or the `run_query` MCP):

```sql
-- eBPF-generated traces show up under the Beyla service name
SELECT Timestamp, ServiceName, SpanName, SpanKind
FROM otel.otel_traces
WHERE ServiceName = 'otel-agent-ebpf'
ORDER BY Timestamp DESC
LIMIT 20;

-- row count for the eBPF service
SELECT count() FROM otel.otel_traces WHERE ServiceName = 'otel-agent-ebpf';
```

You should see spans like `GET /health` produced entirely by eBPF — the app
itself was never modified or configured to emit telemetry.

## Instrumenting a different app

Beyla selects the target by the port it listens on. To instrument something
other than the bundled FastAPI app, either:

- point `BEYLA_OPEN_PORT` (in `docker-compose.ebpf.yml`) at another service's
  port and share that service's PID namespace (`pid: "service:<name>"`), or
- select by executable path with `BEYLA_AUTO_TARGET_EXE` instead of the port.

See the [Beyla configuration options](https://grafana.com/docs/beyla/latest/configure/options/).

## Troubleshooting

- **Beyla exits with a permissions/capabilities error** — the container must be
  `privileged: true` (already set) and the host must be a real Linux kernel with
  eBPF. Confirm `/sys/kernel/btf/vmlinux` exists.
- **No spans in ClickHouse** — check the `collector` logs for ClickHouse errors,
  and make sure `.env.ebpf` has valid credentials. Also confirm you generated
  traffic on port 8000.
- **Collector TLS error to ClickHouse Cloud** — the ClickHouse exporter
  (v0.129.0) validates the server certificate. If your network runs a TLS
  intercepting proxy (common on corporate networks), the handshake can fail. Run
  from a network without interception, or add your corporate root CA to the
  collector image's trust store. (This exporter version has no
  `insecure_skip_verify` option.)
- **`pid: "service:app"` errors** — ensure the `app` service is up first;
  `depends_on` handles ordering, but on a cold build the app image may take a
  while to build.
