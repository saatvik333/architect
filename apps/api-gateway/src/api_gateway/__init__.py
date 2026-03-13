"""ARCHITECT API Gateway — unified HTTP entry point for the ARCHITECT system."""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(
    title="ARCHITECT API Gateway",
    description="Unified entry point for the ARCHITECT autonomous coding system.",
    version="0.1.0",
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Aggregate health check across all backend services."""
    return {"status": "healthy"}


@app.post("/api/v1/tasks")
async def create_task(payload: dict) -> dict[str, str]:  # type: ignore[type-arg]
    """Submit a new task specification."""
    # TODO: forward to task-graph-engine
    return {"task_id": "stub", "status": "accepted"}


@app.get("/api/v1/tasks/{task_id}")
async def get_task(task_id: str) -> dict[str, str]:
    """Retrieve task status."""
    # TODO: forward to task-graph-engine
    return {"id": task_id, "status": "pending"}


@app.get("/api/v1/tasks/{task_id}/logs")
async def get_task_logs(task_id: str, follow: bool = False) -> dict:  # type: ignore[type-arg]
    """Retrieve logs for a task."""
    # TODO: forward to logging service
    return {"task_id": task_id, "entries": []}
