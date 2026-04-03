"""Tests for Deployment Pipeline API routes."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from deployment_pipeline.api.dependencies import set_pipeline_manager
from deployment_pipeline.config import DeploymentPipelineConfig
from deployment_pipeline.pipeline_manager import PipelineManager


@pytest.fixture
def app(config: DeploymentPipelineConfig, mock_temporal_client: AsyncMock):
    """Create a test app with DI wired (no lifespan to avoid Redis/Temporal)."""
    from fastapi import FastAPI

    from deployment_pipeline.api.routes import router

    manager = PipelineManager(config=config, temporal_client=mock_temporal_client)
    set_pipeline_manager(manager)

    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


@pytest.fixture
async def client(app):
    """Return an async HTTP client wired to the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestRoutes:
    """Tests for the Deployment Pipeline HTTP API."""

    async def test_health_check(self, client: AsyncClient) -> None:
        """GET /health should return healthy status."""
        response = await client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] in ("healthy", "degraded")
        assert body["service"] == "deployment-pipeline"
        assert "uptime_seconds" in body

    async def test_start_deployment(self, client: AsyncClient) -> None:
        """POST /api/v1/deployments should create a deployment."""
        response = await client.post(
            "/api/v1/deployments",
            json={
                "task_id": "task-test-123",
                "artifact_ref": "registry/app:v1.0.0",
                "eval_report_summary": "All layers passed.",
                "confidence": 0.98,
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert "deployment_id" in body
        assert body["status"] == "pending"

    async def test_get_deployment(self, client: AsyncClient) -> None:
        """GET /api/v1/deployments/{id} should return the deployment state."""
        # First create a deployment.
        create_resp = await client.post(
            "/api/v1/deployments",
            json={
                "task_id": "task-get-test",
                "artifact_ref": "registry/app:v2.0.0",
            },
        )
        deployment_id = create_resp.json()["deployment_id"]

        # Then retrieve it.
        response = await client.get(f"/api/v1/deployments/{deployment_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["deployment_id"] == deployment_id

    async def test_get_deployment_not_found(self, client: AsyncClient) -> None:
        """GET /api/v1/deployments/{id} should 404 for unknown IDs."""
        response = await client.get("/api/v1/deployments/deploy-nonexistent")
        assert response.status_code == 404

    async def test_list_deployments_empty(self, client: AsyncClient) -> None:
        """GET /api/v1/deployments should return an empty list initially."""
        response = await client.get("/api/v1/deployments")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_list_deployments_with_items(self, client: AsyncClient) -> None:
        """GET /api/v1/deployments should list created deployments."""
        for i in range(3):
            await client.post(
                "/api/v1/deployments",
                json={
                    "task_id": f"task-list-{i}",
                    "artifact_ref": f"registry/app:v{i}",
                },
            )

        response = await client.get("/api/v1/deployments")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 3

    async def test_list_deployments_pagination(self, client: AsyncClient) -> None:
        """GET /api/v1/deployments with offset/limit should paginate."""
        for i in range(5):
            await client.post(
                "/api/v1/deployments",
                json={
                    "task_id": f"task-page-{i}",
                    "artifact_ref": f"registry/app:v{i}",
                },
            )

        response = await client.get("/api/v1/deployments", params={"offset": 1, "limit": 2})
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2

    async def test_rollback_deployment(self, client: AsyncClient) -> None:
        """POST /api/v1/deployments/{id}/rollback should trigger rollback."""
        create_resp = await client.post(
            "/api/v1/deployments",
            json={
                "task_id": "task-rollback",
                "artifact_ref": "registry/app:v1",
            },
        )
        deployment_id = create_resp.json()["deployment_id"]

        response = await client.post(
            f"/api/v1/deployments/{deployment_id}/rollback",
            json={"reason": "manual"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True

    async def test_cancel_deployment(self, client: AsyncClient) -> None:
        """POST /api/v1/deployments/{id}/cancel should cancel."""
        create_resp = await client.post(
            "/api/v1/deployments",
            json={
                "task_id": "task-cancel",
                "artifact_ref": "registry/app:v1",
            },
        )
        deployment_id = create_resp.json()["deployment_id"]

        response = await client.post(f"/api/v1/deployments/{deployment_id}/cancel")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
