"""Tests for Task Graph Engine API routes."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from architect_common.enums import HealthStatus
from task_graph_engine.api.dependencies import get_config, get_decomposer, get_task_dag
from task_graph_engine.config import TaskGraphEngineConfig
from task_graph_engine.decomposer import TaskDecomposer
from task_graph_engine.graph import TaskDAG
from task_graph_engine.service import create_app


@pytest.fixture
def app():
    """Create a fresh app with a clean in-memory DAG."""
    application = create_app()

    # Provide a fresh DAG and decomposer per test so tests are isolated.
    dag = TaskDAG()
    decomposer = TaskDecomposer()

    application.dependency_overrides[get_task_dag] = lambda: dag
    application.dependency_overrides[get_decomposer] = lambda: decomposer
    application.dependency_overrides[get_config] = lambda: TaskGraphEngineConfig()

    return application


@pytest.fixture
async def client(app):
    """Return an async HTTP client wired to the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _sample_spec() -> dict:
    """Return a minimal spec for decomposition."""
    return {
        "intent": "Add a greeting endpoint",
        "constraints": [],
        "success_criteria": [
            {"description": "Returns 200", "test_type": "unit", "automated": True}
        ],
        "file_targets": ["src/hello.py"],
    }


class TestRoutes:
    """Tests for Task Graph Engine API routes."""

    async def test_health_check(self, client: AsyncClient) -> None:
        """GET /health returns healthy status."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == HealthStatus.HEALTHY
        assert data["service"] == "task-graph-engine"

    async def test_submit_spec(self, client: AsyncClient) -> None:
        """POST /tasks/submit decomposes a spec into tasks."""
        resp = await client.post(
            "/tasks/submit",
            json={"spec": _sample_spec()},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["task_count"] >= 1
        assert len(data["task_ids"]) == data["task_count"]
        assert isinstance(data["execution_order"], list)

    async def test_list_tasks_empty(self, client: AsyncClient) -> None:
        """GET /tasks returns an empty list when no tasks exist."""
        resp = await client.get("/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tasks"] == []
        assert data["total"] == 0

    async def test_list_tasks_after_submit(self, client: AsyncClient) -> None:
        """GET /tasks returns tasks after a spec has been submitted."""
        await client.post("/tasks/submit", json={"spec": _sample_spec()})

        resp = await client.get("/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert len(data["tasks"]) == data["total"]
        # Each task has expected fields.
        task = data["tasks"][0]
        assert "id" in task
        assert "type" in task
        assert "status" in task
        assert "description" in task

    async def test_get_task_by_id(self, client: AsyncClient) -> None:
        """GET /tasks/{task_id} returns a specific task."""
        submit_resp = await client.post("/tasks/submit", json={"spec": _sample_spec()})
        task_id = submit_resp.json()["task_ids"][0]

        resp = await client.get(f"/tasks/{task_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == task_id

    async def test_get_task_not_found(self, client: AsyncClient) -> None:
        """GET /tasks/{task_id} returns 404 for unknown task."""
        resp = await client.get("/tasks/task-nonexistent0")
        assert resp.status_code == 404

    async def test_get_graph_empty(self, client: AsyncClient) -> None:
        """GET /graph returns empty graph when no tasks exist."""
        resp = await client.get("/graph")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_count"] == 0
        assert data["tasks"] == []

    async def test_get_graph_after_submit(self, client: AsyncClient) -> None:
        """GET /graph returns the full graph state after submission."""
        await client.post("/tasks/submit", json={"spec": _sample_spec()})

        resp = await client.get("/graph")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_count"] >= 1
        assert len(data["tasks"]) == data["task_count"]
        assert isinstance(data["execution_order"], list)
        assert isinstance(data["validation_errors"], list)
