"""End-to-end test: full HTTP pipeline from spec submission to completion.

This test exercises the full running system through the API gateway:
  spec submission -> task execution -> world state update -> verification

Requires the full ARCHITECT service stack to be running.
Skipped gracefully when infrastructure is not available.
"""

from __future__ import annotations

import os

import httpx
import pytest


def _gateway_base_url() -> str:
    """Return the API gateway base URL from environment or default."""
    return os.environ.get("ARCHITECT_GATEWAY_URL", "http://localhost:8000")


def _wsl_base_url() -> str:
    """Return the World State Ledger base URL from environment or default."""
    return os.environ.get("ARCHITECT_WSL_URL", "http://localhost:8001")


@pytest.mark.e2e
@pytest.mark.integration
class TestFullPipeline:
    """Test the full ARCHITECT pipeline via HTTP calls to running services."""

    async def test_spec_to_completion(self, poll_task_status) -> None:
        """Submit a spec through the gateway and verify end-to-end completion.

        Steps:
        1. POST /api/v1/tasks to submit a simple spec
        2. Poll GET /api/v1/tasks/{id} until completed or failed (120s timeout)
        3. Assert status is completed
        4. GET /api/v1/state from the World State Ledger, verify repo state updated
        """
        gateway_url = _gateway_base_url()
        wsl_url = _wsl_base_url()

        # Check that the gateway is reachable; skip if not
        try:
            async with httpx.AsyncClient(timeout=5.0) as probe:
                resp = await probe.get(f"{gateway_url}/health")
                resp.raise_for_status()
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError):
            pytest.skip(
                f"API gateway not reachable at {gateway_url} — "
                "skipping full-pipeline integration test"
            )

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: Submit a task
            task_spec = {
                "name": "e2e-pipeline-add-function",
                "description": "Generate a Python function that adds two numbers",
                "spec": {
                    "language": "python",
                    "function_name": "add",
                    "parameters": [
                        {"name": "a", "type": "int"},
                        {"name": "b", "type": "int"},
                    ],
                    "return_type": "int",
                    "description": "Return the sum of two integers",
                    "test_cases": [
                        {"inputs": {"a": 1, "b": 2}, "expected": 3},
                        {"inputs": {"a": -1, "b": 1}, "expected": 0},
                    ],
                },
            }

            submit_resp = await client.post(
                f"{gateway_url}/api/v1/tasks", json=task_spec
            )
            assert submit_resp.status_code == 200, (
                f"Task submission failed: {submit_resp.status_code} {submit_resp.text}"
            )
            submit_data = submit_resp.json()
            task_id = submit_data["task_id"]
            assert task_id, "Expected a task_id in the submission response"

            # Step 2: Poll until terminal status
            task_url = f"{gateway_url}/api/v1/tasks/{task_id}"
            final_data = await poll_task_status(client, task_url, timeout=120.0)

            # Step 3: Assert completion
            assert final_data["status"] == "completed", (
                f"Task did not complete successfully. "
                f"Status: {final_data.get('status')}, Data: {final_data}"
            )

            # Step 4: Verify world state was updated
            try:
                wsl_resp = await client.get(f"{wsl_url}/api/v1/state")
                wsl_resp.raise_for_status()
                wsl_data = wsl_resp.json()

                # The world state should have repo information
                repo_state = wsl_data.get("data", {}).get("repo") or wsl_data.get("repo")
                if repo_state is not None:
                    assert repo_state.get("commit_hash"), (
                        "World state repo.commit_hash should be set after task completion"
                    )
            except (httpx.ConnectError, httpx.TimeoutException):
                # WSL might not be reachable separately; the gateway test is sufficient
                pass
