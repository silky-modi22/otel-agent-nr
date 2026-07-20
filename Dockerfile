# Production image: single container running the FastAPI dashboard/ingest
# server. The server spawns the bundled OpenTelemetry Collector (otel-custom,
# built with the ClickHouse + OTLP exporters) as a child process on :4318 when
# a collector mode is started from the dashboard.

# ---- Stage 1: build the custom collector (otel-custom) ----
FROM otel/opentelemetry-collector-builder:0.129.0 AS collector-build
WORKDIR /build
COPY collector/builder-config.yaml /build/collector/builder-config.yaml
RUN mkdir -p dist && ocb --config=/build/collector/builder-config.yaml

# ---- Stage 2: python runtime + app + collector binary ----
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# tini is a minimal init that runs as PID 1 to reap zombie children and forward
# signals. Without it, uvicorn runs as PID 1 and asyncio.create_subprocess_exec
# (used to spawn the collector and pipeline jobs) hangs because there is no init
# to handle SIGCHLD / reap children.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App source.
COPY agent ./agent
COPY collector ./collector
COPY examples ./examples
COPY app.py ./app.py

# Bundled collector binary (must be executable so ProcessManager can find it).
COPY --from=collector-build /build/dist/otel-custom/otel-custom /app/dist/otel-custom/otel-custom
RUN chmod +x /app/dist/otel-custom/otel-custom

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Documented default; platforms (Railway/Render/Fly) inject $PORT at runtime.
ENV PORT=8000
EXPOSE 8000

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/docker-entrypoint.sh"]
