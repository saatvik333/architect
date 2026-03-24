"""ARCHITECT observability: OpenTelemetry tracing + Prometheus metrics."""

from architect_observability.setup import init_observability, shutdown_observability

__all__ = ["init_observability", "shutdown_observability"]
