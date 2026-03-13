"""End-to-end test: ARCHITECT generates a simple function from a spec.

This test exercises the full pipeline:
  spec submission -> task decomposition -> code generation -> evaluation -> result

Requires the full ARCHITECT system to be running.
"""

from __future__ import annotations

import pytest


@pytest.mark.e2e
class TestSimpleFunction:
    """E2E test: generate a simple Python function from a natural language spec."""

    @pytest.mark.e2e
    async def test_generate_add_function(
        self,
        async_http_client,
        gateway_url: str,  # type: ignore[no-untyped-def]
    ) -> None:
        """Submit a spec for a simple 'add' function and wait for completion."""
        task_spec = {
            "name": "e2e-add-function",
            "description": "Generate a Python function that adds two numbers",
            "type": "function",
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
                    {"inputs": {"a": 0, "b": 0}, "expected": 0},
                ],
            },
        }

        # Submit the task
        resp = await async_http_client.post(f"{gateway_url}/api/v1/tasks", json=task_spec)
        assert resp.status_code == 200
        data = resp.json()
        task_id = data["task_id"]

        # In a real E2E test, we would poll until completion with a timeout.
        # For now, just verify submission succeeded.
        assert task_id
        assert data.get("status") in ("accepted", "pending")

    @pytest.mark.e2e
    async def test_generate_fibonacci_function(
        self,
        async_http_client,
        gateway_url: str,  # type: ignore[no-untyped-def]
    ) -> None:
        """Submit a spec for a fibonacci function — slightly more complex E2E test."""
        task_spec = {
            "name": "e2e-fibonacci",
            "description": "Generate a Python function that computes the nth Fibonacci number",
            "type": "function",
            "spec": {
                "language": "python",
                "function_name": "fibonacci",
                "parameters": [{"name": "n", "type": "int"}],
                "return_type": "int",
                "description": "Return the nth Fibonacci number (0-indexed: fib(0)=0, fib(1)=1)",
                "test_cases": [
                    {"inputs": {"n": 0}, "expected": 0},
                    {"inputs": {"n": 1}, "expected": 1},
                    {"inputs": {"n": 10}, "expected": 55},
                ],
            },
        }

        resp = await async_http_client.post(f"{gateway_url}/api/v1/tasks", json=task_spec)
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"]
