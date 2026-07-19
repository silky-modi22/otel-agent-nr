"""Minimal real Google Gemini call with OpenTelemetry GenAI instrumentation.

Exports OTLP over HTTP. Requires: GEMINI_API_KEY (or GOOGLE_API_KEY).
Optional: OTEL_EXPORTER_OTLP_ENDPOINT (default http://localhost:4318),
          OTEL_SERVICE_NAME, DEPLOYMENT_ENVIRONMENT,
          GEMINI_EXAMPLE_MODEL, GEMINI_EXAMPLE_PROMPT,
          TRACELOOP_TRACE_CONTENT (default "false")

Uses the Traceloop instrumentation
`opentelemetry-instrumentation-google-generativeai`, which instruments the
classic `google-generativeai` SDK (import `google.generativeai`), NOT the
newer `google-genai` SDK.
"""

from __future__ import annotations

import os
import sys

# Use the OS trust store (Windows cert store) so corporate TLS proxies with a
# self-signed root CA don't break the HTTPS call to generativelanguage.googleapis.com.
# Best-effort: no-op if truststore isn't installed.
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001 - optional dependency, never fatal
    pass

import google.generativeai as genai
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.google_generativeai import (
    GoogleGenerativeAiInstrumentor,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def _normalize_endpoint(raw: str) -> str:
    return raw.strip().rstrip("/") + "/"


def main() -> None:
    # Same env var as the rest of the repo; fall back to GOOGLE_API_KEY.
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: Set GEMINI_API_KEY (or GOOGLE_API_KEY).", file=sys.stderr)
        raise SystemExit(1)

    # Content capture is off by default for safety; let the user opt in.
    os.environ.setdefault("TRACELOOP_TRACE_CONTENT", "false")

    raw_ep = os.environ.get(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://localhost:4318",
    )
    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = _normalize_endpoint(raw_ep)

    service_name = os.environ.get("OTEL_SERVICE_NAME", "gemini-otel-example")
    environment = os.environ.get("DEPLOYMENT_ENVIRONMENT", "dev")
    resource = Resource.create(
        {
            "service.name": service_name,
            "deployment.environment": environment,
        }
    )

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(),
        export_interval_millis=5000,
    )
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[metric_reader],
    )
    metrics.set_meter_provider(meter_provider)

    GoogleGenerativeAiInstrumentor().instrument()

    genai.configure(api_key=api_key)
    model_name = os.environ.get("GEMINI_EXAMPLE_MODEL", "gemini-2.5-flash")
    prompt = os.environ.get(
        "GEMINI_EXAMPLE_PROMPT",
        "Reply in one short sentence: what is OpenTelemetry used for?",
    )

    print(f"Calling Gemini model={model_name!r} …", flush=True)
    exit_code = 0
    try:
        model = genai.GenerativeModel(model_name)
        resp = model.generate_content(prompt)
        text = (getattr(resp, "text", "") or "").strip()
        print("Assistant:", text[:500], flush=True)
    except Exception as exc:  # noqa: BLE001 - report + still export the span
        exit_code = 1
        print(f"Gemini call failed: {exc}", file=sys.stderr, flush=True)
    finally:
        # Always flush so the span (success OR error) reaches the collector.
        tracer_provider.force_flush()
        meter_provider.force_flush()
        tracer_provider.shutdown()
        meter_provider.shutdown()
        print(
            "OTLP export flushed. Check collector / ClickHouse / New Relic "
            "for traces and metrics.",
            flush=True,
        )

    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
