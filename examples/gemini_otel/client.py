"""Real Google Gemini call instrumented with OpenTelemetry, exported over OTLP/HTTP.

Requires: GEMINI_API_KEY (or GOOGLE_API_KEY).
Optional: OTEL_EXPORTER_OTLP_ENDPOINT (default http://localhost:4318),
          OTEL_SERVICE_NAME, DEPLOYMENT_ENVIRONMENT,
          GEMINI_EXAMPLE_MODEL, GEMINI_EXAMPLE_PROMPT,
          GEMINI_TRACE_CONTENT (default "false")

Uses the MODERN `google-genai` SDK (import `google.genai`) together with the
OFFICIAL OpenTelemetry GenAI instrumentation
`opentelemetry-instrumentation-google-genai` (import
`opentelemetry.instrumentation.google_genai.GoogleGenAiSdkInstrumentor`), which
emits gen_ai.* semantic-convention spans/metrics for generate_content calls.

Robustness: in addition to auto-instrumentation, this script ALWAYS wraps the
call in an explicit manual span ("gemini.generate_content") so at least one
trace row lands in the backend even if auto-instrumentation emits nothing.
"""

from __future__ import annotations

import os
import sys
import time

# Use the OS trust store (Windows cert store) so corporate TLS proxies with a
# self-signed root CA don't break the HTTPS call to generativelanguage.googleapis.com.
# Best-effort: no-op if truststore isn't installed.
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001 - optional dependency, never fatal
    pass

from google import genai
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def _normalize_endpoint(raw: str) -> str:
    return raw.strip().rstrip("/") + "/"


def _instrument_google_genai() -> bool:
    """Enable official OTel GenAI auto-instrumentation. Best-effort.

    Returns True if the instrumentor was applied, False otherwise. A failure
    here is non-fatal because the explicit manual span still guarantees a row.
    """
    try:
        from opentelemetry.instrumentation.google_genai import (
            GoogleGenAiSdkInstrumentor,
        )

        GoogleGenAiSdkInstrumentor().instrument()
        return True
    except Exception as exc:  # noqa: BLE001 - fall back to manual span only
        print(f"google-genai auto-instrumentation unavailable: {exc}", flush=True)
        return False


def main() -> None:
    # Same env var as the rest of the repo; fall back to GOOGLE_API_KEY.
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: Set GEMINI_API_KEY (or GOOGLE_API_KEY).", file=sys.stderr)
        raise SystemExit(1)

    # Content capture is off by default for safety; let the user opt in.
    # Map the repo's GEMINI_TRACE_CONTENT toggle onto the official instrumentation
    # env var (OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT).
    capture_content = os.environ.get("GEMINI_TRACE_CONTENT", "false").strip().lower()
    if capture_content in {"1", "true", "yes", "on"}:
        os.environ.setdefault(
            "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "SPAN_ONLY"
        )
    else:
        os.environ.setdefault(
            "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "NO_CONTENT"
        )

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

    # Auto-instrumentation (emits gen_ai.* spans). Non-fatal if unavailable.
    auto_ok = _instrument_google_genai()

    tracer = trace.get_tracer("gemini-otel-example")

    model_name = os.environ.get("GEMINI_EXAMPLE_MODEL", "gemini-2.5-flash")
    prompt = os.environ.get(
        "GEMINI_EXAMPLE_PROMPT",
        "Reply in one short sentence: what is OpenTelemetry used for?",
    )

    client = genai.Client(api_key=api_key)

    print(
        f"Calling Gemini model={model_name!r} (auto_instrumentation={auto_ok}) …",
        flush=True,
    )
    exit_code = 0
    # Explicit manual span GUARANTEES a trace row even if auto-instrumentation
    # emits nothing. Auto-instrumentation (if present) nests under this span.
    with tracer.start_as_current_span("gemini.generate_content") as span:
        span.set_attribute("gen_ai.system", "gemini")
        span.set_attribute("gen_ai.operation.name", "generate_content")
        span.set_attribute("gen_ai.request.model", model_name)
        span.set_attribute("prompt.length", len(prompt))
        start = time.perf_counter()
        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            latency_ms = (time.perf_counter() - start) * 1000.0
            text = (getattr(resp, "text", "") or "").strip()
            span.set_attribute("response.length", len(text))
            span.set_attribute("latency_ms", round(latency_ms, 2))

            usage = getattr(resp, "usage_metadata", None)
            if usage is not None:
                prompt_tokens = getattr(usage, "prompt_token_count", None)
                output_tokens = getattr(usage, "candidates_token_count", None)
                total_tokens = getattr(usage, "total_token_count", None)
                if prompt_tokens is not None:
                    span.set_attribute("gen_ai.usage.input_tokens", int(prompt_tokens))
                if output_tokens is not None:
                    span.set_attribute(
                        "gen_ai.usage.output_tokens", int(output_tokens)
                    )
                if total_tokens is not None:
                    span.set_attribute("gen_ai.usage.total_tokens", int(total_tokens))

            span.set_status(trace.Status(trace.StatusCode.OK))
            print("Assistant:", text[:500], flush=True)
        except Exception as exc:  # noqa: BLE001 - record + still export the span
            exit_code = 1
            latency_ms = (time.perf_counter() - start) * 1000.0
            span.set_attribute("latency_ms", round(latency_ms, 2))
            span.record_exception(exc)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)))
            print(f"Gemini call failed: {exc}", file=sys.stderr, flush=True)

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
