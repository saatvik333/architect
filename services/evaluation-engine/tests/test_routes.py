"""Tests for Evaluation Engine API routes."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from architect_common.enums import EvalLayer, EvalVerdict, HealthStatus
from evaluation_engine.api.dependencies import get_evaluator
from evaluation_engine.api.routes import _report_store
from evaluation_engine.models import (
    CompilationResult,
    EvaluationReport,
    LayerEvaluation,
)
from evaluation_engine.service import create_app


def _build_mock_evaluator() -> AsyncMock:
    """Build a mock Evaluator that returns a passing report."""
    evaluator = AsyncMock()

    layer = LayerEvaluation(
        layer=EvalLayer.COMPILATION,
        verdict=EvalVerdict.PASS,
        details=CompilationResult(success=True),
    )
    report = EvaluationReport(
        task_id="task-test0001",
        layers=[layer],
        overall_verdict=EvalVerdict.PASS,
    )
    evaluator.evaluate.return_value = report

    return evaluator


@pytest.fixture
def app():
    """Create a fresh app with a mocked evaluator."""
    application = create_app()

    mock_evaluator = _build_mock_evaluator()

    async def _override_evaluator():
        return mock_evaluator

    application.dependency_overrides[get_evaluator] = _override_evaluator
    application.state.mock_evaluator = mock_evaluator

    # Clear the in-memory report store between tests.
    _report_store.clear()

    return application


@pytest.fixture
async def client(app):
    """Return an async HTTP client wired to the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestRoutes:
    """Tests for Evaluation Engine API routes."""

    async def test_health_check(self, client: AsyncClient) -> None:
        """GET /health returns healthy status."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == HealthStatus.HEALTHY
        assert data["service"] == "evaluation-engine"

    async def test_run_evaluation(self, app, client: AsyncClient) -> None:
        """POST /evaluate runs the evaluation pipeline and returns a report."""
        resp = await client.post(
            "/evaluate",
            json={
                "task_id": "task-test0001",
                "sandbox_session_id": "sbx-test000001",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == "task-test0001"
        assert data["overall_verdict"] == EvalVerdict.PASS
        assert data["layers_evaluated"] == 1
        assert "report" in data
        app.state.mock_evaluator.evaluate.assert_awaited_once()

    async def test_run_evaluation_stores_report(self, client: AsyncClient) -> None:
        """POST /evaluate stores the report for later retrieval."""
        await client.post(
            "/evaluate",
            json={
                "task_id": "task-test0001",
                "sandbox_session_id": "sbx-test000001",
            },
        )

        # The report should now be retrievable by the request task_id.
        resp = await client.get("/reports/task-test0001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == "task-test0001"

    async def test_get_report_not_found(self, client: AsyncClient) -> None:
        """GET /reports/{task_id} returns 404 for unknown task."""
        resp = await client.get("/reports/task-nonexistent")
        assert resp.status_code == 404
        assert "No evaluation report found" in resp.json()["detail"]

    async def test_run_evaluation_fail_hard(self, app, client: AsyncClient) -> None:
        """POST /evaluate returns fail_hard verdict when evaluator reports it."""
        fail_layer = LayerEvaluation(
            layer=EvalLayer.UNIT_TESTS,
            verdict=EvalVerdict.FAIL_HARD,
            details=CompilationResult(success=False, errors=["syntax error"]),
        )
        fail_report = EvaluationReport(
            task_id="task-fail0001",
            layers=[fail_layer],
            overall_verdict=EvalVerdict.FAIL_HARD,
        )
        app.state.mock_evaluator.evaluate.return_value = fail_report

        resp = await client.post(
            "/evaluate",
            json={
                "task_id": "task-fail0001",
                "sandbox_session_id": "sbx-test000001",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["overall_verdict"] == EvalVerdict.FAIL_HARD

    async def test_run_evaluation_missing_fields(self, client: AsyncClient) -> None:
        """POST /evaluate returns 422 when required fields are missing."""
        resp = await client.post("/evaluate", json={})
        assert resp.status_code == 422
