"""One-call setup for tracing and metrics on any ARCHITECT FastAPI service."""

from __future__ import annotations

import os

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from prometheus_fastapi_instrumentator import Instrumentator


def init_observability(
    app: FastAPI,
    service_name: str,
    *,
    otlp_endpoint: str = "",
    enable_console_exporter: bool = False,
) -> None:
    """Initialize OpenTelemetry tracing and Prometheus metrics for a FastAPI app.

    Args:
        app: The FastAPI application instance.
        service_name: Logical service name (e.g. "world-state-ledger").
        otlp_endpoint: OTLP gRPC endpoint (e.g. "http://jaeger:4317").
            Falls back to OTEL_EXPORTER_OTLP_ENDPOINT env var, then disables export.
        enable_console_exporter: If True, also export spans to stderr (for dev).
    """
    endpoint = otlp_endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")

    # -- Tracing --
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    if endpoint:
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))

    if enable_console_exporter:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)

    # Auto-instrument FastAPI (creates spans for every request)
    FastAPIInstrumentor.instrument_app(app)

    # Auto-instrument outbound httpx calls (ServiceClient uses httpx)
    HTTPXClientInstrumentor().instrument()

    # Store provider on app state for shutdown
    app.state.tracer_provider = provider

    # -- Metrics --
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=["/health", "/metrics"],
    )
    instrumentator.instrument(app)
    instrumentator.expose(app, endpoint="/metrics")


def shutdown_observability(app: FastAPI) -> None:
    """Flush and shut down the tracer provider."""
    provider = getattr(app.state, "tracer_provider", None)
    if provider is not None and hasattr(provider, "shutdown"):
        provider.shutdown()
