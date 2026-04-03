"""Tests for Failure Taxonomy API routes."""

from __future__ import annotations

import os

os.environ.setdefault("ARCHITECT_PG_PASSWORD", "test_password")

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from architect_common.enums import FailureCode, HealthStatus
from failure_taxonomy.classifier import FailureClassifier
from failure_taxonomy.config import FailureTaxonomyConfig
from failure_taxonomy.post_mortem_analyzer import PostMortemAnalyzer
from failure_taxonomy.simulation_runner import SimulationRunner


@pytest.fixture
def app() -> object:
    """Create a test FastAPI app with mocked dependencies."""
    import time

    from fastapi import FastAPI

    from failure_taxonomy.api.dependencies import (
        set_classifier,
        set_post_mortem_analyzer,
        set_session_factory,
        set_simulation_runner,
    )
    from failure_taxonomy.api.routes import router

    app = FastAPI()
    app.state.started_at = time.monotonic()
    app.include_router(router)

    # Set up mocked dependencies
    config = FailureTaxonomyConfig(use_llm_classification=False)
    classifier = FailureClassifier(config, llm_client=None)
    set_classifier(classifier)
    set_post_mortem_analyzer(PostMortemAnalyzer(llm_client=None))
    set_simulation_runner(SimulationRunner())

    # Mock session factory
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.flush = AsyncMock()

    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)
    set_session_factory(mock_factory)

    return app


@pytest.fixture
def client(app: object) -> TestClient:
    """Return a test client for the app."""
    from fastapi import FastAPI

    assert isinstance(app, FastAPI)
    return TestClient(app)


class TestHealthEndpoint:
    """Test the health check endpoint."""

    def test_health_check(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "failure-taxonomy"
        assert data["status"] == HealthStatus.HEALTHY


class TestClassifyEndpoint:
    """Test the POST /api/v1/failures/classify endpoint."""

    def test_classify_import_error(self, client: TestClient) -> None:
        """Classify an ImportError."""
        with patch("failure_taxonomy.api.routes.FailureRecordRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.create = AsyncMock()
            mock_repo_cls.return_value = mock_repo

            response = client.post(
                "/api/v1/failures/classify",
                json={
                    "task_id": "task-1",
                    "error_message": "ImportError: No module named 'pandas'",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["failure_code"] == FailureCode.F5_DEPENDENCY_ISSUE
        assert data["task_id"] == "task-1"

    def test_classify_syntax_error(self, client: TestClient) -> None:
        """Classify a SyntaxError."""
        with patch("failure_taxonomy.api.routes.FailureRecordRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.create = AsyncMock()
            mock_repo_cls.return_value = mock_repo

            response = client.post(
                "/api/v1/failures/classify",
                json={
                    "task_id": "task-2",
                    "error_message": "SyntaxError: invalid syntax",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["failure_code"] == FailureCode.F6_LOGIC_BUG


class TestFailuresEndpoints:
    """Test failure listing and stats endpoints."""

    def test_list_failures(self, client: TestClient) -> None:
        with patch("failure_taxonomy.api.routes.FailureRecordRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.get_recent = AsyncMock(return_value=[])
            mock_repo_cls.return_value = mock_repo

            response = client.get("/api/v1/failures")

        assert response.status_code == 200
        assert response.json() == []

    def test_get_failure_stats(self, client: TestClient) -> None:
        with patch("failure_taxonomy.api.routes.FailureRecordRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.get_stats_by_code = AsyncMock(
                return_value={"f6_logic_bug": 5, "f5_dependency_issue": 2}
            )
            mock_repo_cls.return_value = mock_repo

            response = client.get("/api/v1/failures/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 7

    def test_get_failure_not_found(self, client: TestClient) -> None:
        with patch("failure_taxonomy.api.routes.FailureRecordRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.get = AsyncMock(return_value=None)
            mock_repo_cls.return_value = mock_repo

            response = client.get("/api/v1/failures/nonexistent")

        assert response.status_code == 404
