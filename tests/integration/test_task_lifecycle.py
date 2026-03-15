"""Integration test: basic task lifecycle through the ARCHITECT system.

Requires running infrastructure (Postgres, Redis) and the API gateway.
"""

from __future__ import annotations

import pytest


@pytest.mark.integration
class TestTaskLifecycle:
    """Test the full lifecycle of a task: submit -> poll status -> completion."""

    @pytest.mark.integration
    async def test_submit_and_query_task(
        self,
        async_http_client,
        gateway_url: str,  # type: ignore[no-untyped-def]
    ) -> None:
        """Submit a minimal task spec and verify it can be queried."""
        task_spec = {
            "name": "integration-test-task",
            "description": "A simple test task for integration testing",
            "type": "function",
            "spec": {
                "language": "python",
                "function_name": "add",
                "parameters": [
                    {"name": "a", "type": "int"},
                    {"name": "b", "type": "int"},
                ],
                "return_type": "int",
                "description": "Return the sum of a and b",
            },
        }

        # Submit the task
        resp = await async_http_client.post(f"{gateway_url}/api/v1/tasks", json=task_spec)
        assert resp.status_code == 200
        data = resp.json()
        task_id = data["task_id"]
        assert task_id

        # Query the task status
        resp = await async_http_client.get(f"{gateway_url}/api/v1/tasks/{task_id}")
        assert resp.status_code == 200
        status_data = resp.json()
        assert status_data["task_id"] == task_id
        assert status_data["status"] in ("pending", "running", "completed")

    @pytest.mark.integration
    async def test_health_endpoint(
        self,
        async_http_client,
        gateway_url: str,  # type: ignore[no-untyped-def]
    ) -> None:
        """Verify the gateway health endpoint responds."""
        resp = await async_http_client.get(f"{gateway_url}/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
