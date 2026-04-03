"""Tests for BudgetRecordRepository, AgentEfficiencyRepository, and EnforcementActionRepository.

Uses AsyncMock sessions to validate query construction and method behaviour
without requiring a live database.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from architect_db.models.budget import AgentEfficiency, BudgetRecord, EnforcementAction
from architect_db.repositories.budget_repo import (
    AgentEfficiencyRepository,
    BudgetRecordRepository,
    EnforcementActionRepository,
)

# ── Helpers ──────────────────────────────────────────────────────


def _mock_session() -> AsyncMock:
    """Create a mock AsyncSession with common methods."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _mock_scalars(items: list) -> MagicMock:
    """Create a mock result with scalars().all() and scalars().first()."""
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = items
    scalars_mock.first.return_value = items[0] if items else None

    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    return result_mock


# ── BudgetRecordRepository ──────────────────────────────────────


class TestBudgetRecordRepository:
    @pytest.mark.asyncio
    async def test_get_by_id_found(self) -> None:
        session = _mock_session()
        record = BudgetRecord(
            id="br-1",
            project_id="proj-1",
            allocated_tokens=100000,
            consumed_tokens=5000,
        )
        session.get.return_value = record

        repo = BudgetRecordRepository(session)
        result = await repo.get_by_id("br-1")

        assert result is record
        session.get.assert_called_once_with(BudgetRecord, "br-1")

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self) -> None:
        session = _mock_session()
        session.get.return_value = None

        repo = BudgetRecordRepository(session)
        result = await repo.get_by_id("br-nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_create(self) -> None:
        session = _mock_session()
        record = BudgetRecord(
            id="br-1",
            project_id="proj-1",
            allocated_tokens=100000,
            consumed_tokens=0,
        )

        repo = BudgetRecordRepository(session)
        result = await repo.create(record)

        session.add.assert_called_once_with(record)
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once_with(record)
        assert result is record

    @pytest.mark.asyncio
    async def test_get_latest_by_project(self) -> None:
        session = _mock_session()
        record = BudgetRecord(
            id="br-2",
            project_id="proj-1",
            allocated_tokens=100000,
            consumed_tokens=50000,
        )
        session.execute.return_value = _mock_scalars([record])

        repo = BudgetRecordRepository(session)
        result = await repo.get_latest_by_project("proj-1")

        assert result is record

    @pytest.mark.asyncio
    async def test_get_latest_by_project_not_found(self) -> None:
        session = _mock_session()
        session.execute.return_value = _mock_scalars([])

        repo = BudgetRecordRepository(session)
        result = await repo.get_latest_by_project("proj-nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_project(self) -> None:
        session = _mock_session()
        records = [
            BudgetRecord(
                id="br-1", project_id="proj-1", allocated_tokens=100000, consumed_tokens=5000
            ),
            BudgetRecord(
                id="br-2", project_id="proj-1", allocated_tokens=100000, consumed_tokens=10000
            ),
        ]
        session.execute.return_value = _mock_scalars(records)

        repo = BudgetRecordRepository(session)
        result = await repo.get_by_project("proj-1")

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_by_project_empty(self) -> None:
        session = _mock_session()
        session.execute.return_value = _mock_scalars([])

        repo = BudgetRecordRepository(session)
        result = await repo.get_by_project("proj-nonexistent")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_by_project_with_limit(self) -> None:
        session = _mock_session()
        records = [
            BudgetRecord(
                id="br-1", project_id="proj-1", allocated_tokens=100000, consumed_tokens=5000
            ),
        ]
        session.execute.return_value = _mock_scalars(records)

        repo = BudgetRecordRepository(session)
        result = await repo.get_by_project("proj-1", limit=1)

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_all(self) -> None:
        session = _mock_session()
        records = [
            BudgetRecord(
                id="br-1", project_id="proj-1", allocated_tokens=100000, consumed_tokens=5000
            ),
        ]
        session.execute.return_value = _mock_scalars(records)

        repo = BudgetRecordRepository(session)
        result = await repo.list_all()

        assert len(result) == 1


# ── AgentEfficiencyRepository ───────────────────────────────────


class TestAgentEfficiencyRepository:
    @pytest.mark.asyncio
    async def test_get_by_id_found(self) -> None:
        session = _mock_session()
        efficiency = AgentEfficiency(
            id="ae-1",
            agent_id="agent-1",
            agent_type="coder",
            model_tier="tier_2",
            efficiency_score=0.85,
        )
        session.get.return_value = efficiency

        repo = AgentEfficiencyRepository(session)
        result = await repo.get_by_id("ae-1")

        assert result is efficiency

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self) -> None:
        session = _mock_session()
        session.get.return_value = None

        repo = AgentEfficiencyRepository(session)
        result = await repo.get_by_id("ae-nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_latest_by_agent(self) -> None:
        session = _mock_session()
        efficiency = AgentEfficiency(
            id="ae-1",
            agent_id="agent-1",
            agent_type="coder",
            model_tier="tier_2",
            efficiency_score=0.9,
        )
        session.execute.return_value = _mock_scalars([efficiency])

        repo = AgentEfficiencyRepository(session)
        result = await repo.get_latest_by_agent("agent-1")

        assert result is efficiency

    @pytest.mark.asyncio
    async def test_get_latest_by_agent_not_found(self) -> None:
        session = _mock_session()
        session.execute.return_value = _mock_scalars([])

        repo = AgentEfficiencyRepository(session)
        result = await repo.get_latest_by_agent("agent-nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_leaderboard(self) -> None:
        session = _mock_session()
        entries = [
            AgentEfficiency(
                id="ae-1",
                agent_id="agent-1",
                agent_type="coder",
                model_tier="tier_2",
                efficiency_score=0.9,
            ),
            AgentEfficiency(
                id="ae-2",
                agent_id="agent-2",
                agent_type="coder",
                model_tier="tier_1",
                efficiency_score=0.7,
            ),
        ]
        session.execute.return_value = _mock_scalars(entries)

        repo = AgentEfficiencyRepository(session)
        result = await repo.get_leaderboard()

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_leaderboard_empty(self) -> None:
        session = _mock_session()
        session.execute.return_value = _mock_scalars([])

        repo = AgentEfficiencyRepository(session)
        result = await repo.get_leaderboard()

        assert result == []

    @pytest.mark.asyncio
    async def test_get_leaderboard_with_limit(self) -> None:
        session = _mock_session()
        entries = [
            AgentEfficiency(
                id="ae-1",
                agent_id="agent-1",
                agent_type="coder",
                model_tier="tier_2",
                efficiency_score=0.9,
            ),
        ]
        session.execute.return_value = _mock_scalars(entries)

        repo = AgentEfficiencyRepository(session)
        result = await repo.get_leaderboard(limit=1)

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_create(self) -> None:
        session = _mock_session()
        efficiency = AgentEfficiency(
            id="ae-1",
            agent_id="agent-1",
            agent_type="coder",
            model_tier="tier_2",
            efficiency_score=0.85,
        )

        repo = AgentEfficiencyRepository(session)
        result = await repo.create(efficiency)

        session.add.assert_called_once_with(efficiency)
        assert result is efficiency


# ── EnforcementActionRepository ─────────────────────────────────


class TestEnforcementActionRepository:
    @pytest.mark.asyncio
    async def test_get_by_id_found(self) -> None:
        session = _mock_session()
        action = EnforcementAction(
            id="ea-1",
            enforcement_level="alert",
            action_type="throttle",
            budget_consumed_pct=75.0,
        )
        session.get.return_value = action

        repo = EnforcementActionRepository(session)
        result = await repo.get_by_id("ea-1")

        assert result is action

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self) -> None:
        session = _mock_session()
        session.get.return_value = None

        repo = EnforcementActionRepository(session)
        result = await repo.get_by_id("ea-nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_level(self) -> None:
        session = _mock_session()
        actions = [
            EnforcementAction(
                id="ea-1",
                enforcement_level="alert",
                action_type="throttle",
                budget_consumed_pct=75.0,
            ),
        ]
        session.execute.return_value = _mock_scalars(actions)

        repo = EnforcementActionRepository(session)
        result = await repo.get_by_level("alert")

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_by_level_empty(self) -> None:
        session = _mock_session()
        session.execute.return_value = _mock_scalars([])

        repo = EnforcementActionRepository(session)
        result = await repo.get_by_level("halt")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_by_level_with_pagination(self) -> None:
        session = _mock_session()
        actions = [
            EnforcementAction(
                id="ea-1",
                enforcement_level="alert",
                action_type="throttle",
                budget_consumed_pct=75.0,
            ),
        ]
        session.execute.return_value = _mock_scalars(actions)

        repo = EnforcementActionRepository(session)
        result = await repo.get_by_level("alert", limit=10, offset=5)

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_recent(self) -> None:
        session = _mock_session()
        actions = [
            EnforcementAction(
                id="ea-1",
                enforcement_level="alert",
                action_type="throttle",
                budget_consumed_pct=75.0,
            ),
            EnforcementAction(
                id="ea-2",
                enforcement_level="halt",
                action_type="kill",
                budget_consumed_pct=100.0,
            ),
        ]
        session.execute.return_value = _mock_scalars(actions)

        repo = EnforcementActionRepository(session)
        result = await repo.get_recent()

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_recent_empty(self) -> None:
        session = _mock_session()
        session.execute.return_value = _mock_scalars([])

        repo = EnforcementActionRepository(session)
        result = await repo.get_recent()

        assert result == []

    @pytest.mark.asyncio
    async def test_get_recent_with_limit(self) -> None:
        session = _mock_session()
        actions = [
            EnforcementAction(
                id="ea-1",
                enforcement_level="alert",
                action_type="throttle",
                budget_consumed_pct=75.0,
            ),
        ]
        session.execute.return_value = _mock_scalars(actions)

        repo = EnforcementActionRepository(session)
        result = await repo.get_recent(limit=1)

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_create(self) -> None:
        session = _mock_session()
        action = EnforcementAction(
            id="ea-1",
            enforcement_level="alert",
            action_type="throttle",
            budget_consumed_pct=75.0,
        )

        repo = EnforcementActionRepository(session)
        result = await repo.create(action)

        session.add.assert_called_once_with(action)
        assert result is action
