"""Vercel entrypoint for the FastAPI app."""

from __future__ import annotations

import os

from agent.http_app import create_app
from agent.serve import ServeArgs

# Serverless deploys should not block startup on local collector checks.
os.environ.setdefault("SKIP_COLLECTOR_CHECK", "1")

app = create_app()
app.state._serve_args = ServeArgs(
    otlp_endpoint=os.environ.get(
        "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"
    ),
    service_name=os.environ.get("OTEL_SERVICE_NAME", "otel-ai-ingest"),
    environment=os.environ.get("DEPLOYMENT_ENVIRONMENT", "prod"),
    metric_interval_ms=int(os.environ.get("OTEL_METRIC_INTERVAL_MS", "5000")),
    http_host="0.0.0.0",
    http_port=int(os.environ.get("PORT", "8000")),
    gemini_model=os.environ.get("GEMINI_MODEL"),
)
