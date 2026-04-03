"""Tests for Failure Taxonomy Temporal activities."""

from __future__ import annotations

import os

os.environ.setdefault("ARCHITECT_PG_PASSWORD", "test_password")

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from architect_common.enums import FailureCode
from failure_taxonomy.classifier import FailureClassifier
from failure_taxonomy.config import FailureTaxonomyConfig
from failure_taxonomy.post_mortem_analyzer import PostMortemAnalyzer
from failure_taxonomy.simulation_runner import SimulationRunner
from failure_taxonomy.temporal.activities import FailureTaxonomyActivities


@pytest.fixture
def mock_session() -> AsyncMock:
    """Return a mock async session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def mock_session_factory(mock_session: AsyncMock) -> MagicMock:
    """Return a mock session factory."""
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return factory


@pytest.fixture
def activities(mock_session_factory: MagicMock) -> FailureTaxonomyActivities:
    """Return activities with mocked dependencies."""
    config = FailureTaxonomyConfig(use_llm_classification=False)
    classifier = FailureClassifier(config, llm_client=None)
    analyzer = PostMortemAnalyzer(llm_client=None)
    runner = SimulationRunner()
    return FailureTaxonomyActivities(
        classifier=classifier,
        post_mortem_analyzer=analyzer,
        simulation_runner=runner,
        session_factory=mock_session_factory,
    )


class TestClassifyFailureActivity:
    """Test the classify_failure activity."""

    async def test_classify_import_error(self, activities: FailureTaxonomyActivities) -> None:
        """Should classify ImportError as F5."""
        with patch("failure_taxonomy.temporal.activities.FailureRecordRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.create = AsyncMock()
            mock_repo_cls.return_value = mock_repo

            result = await activities.classify_failure(
                {
                    "task_id": "task-1",
                    "error_message": "ImportError: No module named 'foo'",
                }
            )

        assert result["failure_code"] == FailureCode.F5_DEPENDENCY_ISSUE
        assert result["confidence"] >= 0.7
        assert result["failure_record_id"]  # non-empty

    async def test_classify_security_issue(self, activities: FailureTaxonomyActivities) -> None:
        """Should classify security findings as F9."""
        with patch("failure_taxonomy.temporal.activities.FailureRecordRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.create = AsyncMock()
            mock_repo_cls.return_value = mock_repo

            result = await activities.classify_failure(
                {
                    "task_id": "task-2",
                    "error_message": "Security vulnerability found: CVE-2024-0001",
                }
            )

        assert result["failure_code"] == FailureCode.F9_SECURITY_VULN


class TestGetFailureStatsActivity:
    """Test the get_failure_stats activity."""

    async def test_get_stats(self, activities: FailureTaxonomyActivities) -> None:
        """Should return failure statistics."""
        with patch("failure_taxonomy.temporal.activities.FailureRecordRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.get_stats_by_code = AsyncMock(
                return_value={"f6_logic_bug": 3, "f5_dependency_issue": 1}
            )
            mock_repo_cls.return_value = mock_repo

            result = await activities.get_failure_stats({})

        assert result["total"] == 4
        assert result["stats"]["f6_logic_bug"] == 3


class TestRunSimulationActivity:
    """Test the run_simulation activity."""

    async def test_simulation_stub(self, activities: FailureTaxonomyActivities) -> None:
        """Stub simulation should return zero results."""
        result = await activities.run_simulation(
            {
                "source_type": "manual",
                "source_ref": "test",
                "bug_injection_count": 3,
                "max_duration_seconds": 60,
            }
        )
        assert result["detection_rate"] == 0.0
        assert result["failures_injected"] == 0
