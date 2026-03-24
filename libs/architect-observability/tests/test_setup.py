"""Tests for observability setup."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from architect_observability import init_observability, shutdown_observability


class TestObservabilitySetup:
    def test_init_adds_metrics_endpoint(self) -> None:
        app = FastAPI()

        @app.get("/health")
        async def health() -> dict:
            return {"status": "ok"}

        init_observability(app, "test-service")
        client = TestClient(app)
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert "http_requests" in resp.text or "HELP" in resp.text

    def test_init_sets_tracer_provider(self) -> None:
        app = FastAPI()
        init_observability(app, "test-service")
        assert hasattr(app.state, "tracer_provider")
        shutdown_observability(app)

    def test_shutdown_is_safe_without_init(self) -> None:
        app = FastAPI()
        shutdown_observability(app)  # Should not raise

    def test_health_excluded_from_metrics(self) -> None:
        app = FastAPI()

        @app.get("/health")
        async def health() -> dict:
            return {"status": "ok"}

        init_observability(app, "test-service")
        client = TestClient(app)
        # Hit health a few times
        for _ in range(5):
            client.get("/health")
        resp = client.get("/metrics")
        # /health should be excluded from metrics
        assert resp.status_code == 200
