"""Tests for EscalationRepository, ApprovalGateRepository, and ApprovalVoteRepository.

Uses AsyncMock sessions to validate query construction and method behaviour
without requiring a live database.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from architect_db.models.escalation import ApprovalGate, ApprovalVote, Escalation
from architect_db.repositories.escalation_repo import (
    ApprovalGateRepository,
    ApprovalVoteRepository,
    EscalationRepository,
)

# ── Helpers ──────────────────────────────────────────────────────


def _mock_session() -> AsyncMock:
    """Create a mock AsyncSession with common methods."""
    session = AsyncMock()
    session.add = MagicMock()  # session.add() is synchronous in SQLAlchemy
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


def _mock_row(**kwargs: int) -> MagicMock:
    """Create a mock result row with named attributes."""
    row = MagicMock()
    for k, v in kwargs.items():
        setattr(row, k, v)
    return row


# ── EscalationRepository ────────────────────────────────────────


class TestEscalationRepository:
    @pytest.mark.asyncio
    async def test_get_by_id_found(self) -> None:
        session = _mock_session()
        escalation = Escalation(
            id="esc-1",
            summary="test",
            category="ambiguity",
            severity="medium",
            status="pending",
        )
        session.get.return_value = escalation

        repo = EscalationRepository(session)
        result = await repo.get_by_id("esc-1")

        assert result is escalation
        session.get.assert_called_once_with(Escalation, "esc-1")

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self) -> None:
        session = _mock_session()
        session.get.return_value = None

        repo = EscalationRepository(session)
        result = await repo.get_by_id("esc-nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_create_adds_to_session(self) -> None:
        session = _mock_session()
        escalation = Escalation(
            id="esc-2",
            summary="new escalation",
            category="ambiguity",
            severity="high",
            status="pending",
        )

        repo = EscalationRepository(session)
        result = await repo.create(escalation)

        session.add.assert_called_once_with(escalation)
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once_with(escalation)
        assert result is escalation

    @pytest.mark.asyncio
    async def test_get_pending(self) -> None:
        session = _mock_session()
        items = [
            Escalation(
                id="esc-1", summary="a", category="ambiguity", severity="low", status="pending"
            ),
            Escalation(
                id="esc-2", summary="b", category="ambiguity", severity="high", status="pending"
            ),
        ]
        session.execute.return_value = _mock_scalars(items)

        repo = EscalationRepository(session)
        result = await repo.get_pending()

        assert len(result) == 2
        assert all(e.status == "pending" for e in result)

    @pytest.mark.asyncio
    async def test_get_pending_empty(self) -> None:
        session = _mock_session()
        session.execute.return_value = _mock_scalars([])

        repo = EscalationRepository(session)
        result = await repo.get_pending()

        assert result == []

    @pytest.mark.asyncio
    async def test_get_by_status(self) -> None:
        session = _mock_session()
        items = [
            Escalation(
                id="esc-1", summary="a", category="ambiguity", severity="low", status="resolved"
            ),
        ]
        session.execute.return_value = _mock_scalars(items)

        repo = EscalationRepository(session)
        result = await repo.get_by_status("resolved")

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_by_task(self) -> None:
        session = _mock_session()
        items = [
            Escalation(
                id="esc-1",
                summary="a",
                category="ambiguity",
                severity="low",
                status="pending",
                source_task_id="task-123",
            ),
        ]
        session.execute.return_value = _mock_scalars(items)

        repo = EscalationRepository(session)
        result = await repo.get_by_task("task-123")

        assert len(result) == 1
        assert result[0].source_task_id == "task-123"

    @pytest.mark.asyncio
    async def test_get_by_task_empty(self) -> None:
        session = _mock_session()
        session.execute.return_value = _mock_scalars([])

        repo = EscalationRepository(session)
        result = await repo.get_by_task("task-nonexistent")

        assert result == []

    @pytest.mark.asyncio
    async def test_resolve(self) -> None:
        session = _mock_session()
        resolved_escalation = Escalation(
            id="esc-1",
            summary="a",
            category="ambiguity",
            severity="low",
            status="resolved",
            resolved_by="user-1",
            resolution="approved",
        )
        session.execute.return_value = _mock_scalars([resolved_escalation])

        repo = EscalationRepository(session)
        result = await repo.resolve(
            "esc-1",
            resolved_by="user-1",
            resolution="approved",
        )

        assert result is resolved_escalation
        session.execute.assert_awaited_once()
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_resolve_not_found(self) -> None:
        session = _mock_session()
        session.execute.return_value = _mock_scalars([])

        repo = EscalationRepository(session)
        result = await repo.resolve(
            "esc-nonexistent",
            resolved_by="user-1",
            resolution="denied",
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_with_details(self) -> None:
        session = _mock_session()
        resolved = Escalation(
            id="esc-1", summary="a", category="ambiguity", severity="low", status="resolved"
        )
        session.execute.return_value = _mock_scalars([resolved])

        repo = EscalationRepository(session)
        now = datetime.now(tz=UTC)
        result = await repo.resolve(
            "esc-1",
            resolved_by="user-2",
            resolution="override",
            resolution_details={"reason": "urgent"},
            resolved_at=now,
        )

        assert result is resolved

    @pytest.mark.asyncio
    async def test_get_expired_pending(self) -> None:
        session = _mock_session()
        items = [
            Escalation(
                id="esc-1", summary="a", category="ambiguity", severity="low", status="pending"
            ),
        ]
        session.execute.return_value = _mock_scalars(items)

        repo = EscalationRepository(session)
        result = await repo.get_expired_pending()

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_expired_pending_empty(self) -> None:
        session = _mock_session()
        session.execute.return_value = _mock_scalars([])

        repo = EscalationRepository(session)
        result = await repo.get_expired_pending()

        assert result == []

    @pytest.mark.asyncio
    async def test_get_stats(self) -> None:
        session = _mock_session()
        row = _mock_row(total=10, pending=3, resolved=5)
        result_mock = MagicMock()
        result_mock.one.return_value = row
        session.execute.return_value = result_mock

        repo = EscalationRepository(session)
        stats = await repo.get_stats()

        assert stats["total"] == 10
        assert stats["pending"] == 3
        assert stats["resolved"] == 5
        assert stats["expired"] == 2  # 10 - 3 - 5

    @pytest.mark.asyncio
    async def test_get_stats_empty_db(self) -> None:
        session = _mock_session()
        row = _mock_row(total=0, pending=0, resolved=0)
        result_mock = MagicMock()
        result_mock.one.return_value = row
        session.execute.return_value = result_mock

        repo = EscalationRepository(session)
        stats = await repo.get_stats()

        assert stats["total"] == 0
        assert stats["pending"] == 0
        assert stats["resolved"] == 0
        assert stats["expired"] == 0

    @pytest.mark.asyncio
    async def test_list_all(self) -> None:
        session = _mock_session()
        items = [
            Escalation(
                id="esc-1", summary="a", category="ambiguity", severity="low", status="pending"
            ),
        ]
        session.execute.return_value = _mock_scalars(items)

        repo = EscalationRepository(session)
        result = await repo.list_all()

        assert len(result) == 1


# ── ApprovalGateRepository ──────────────────────────────────────


class TestApprovalGateRepository:
    @pytest.mark.asyncio
    async def test_get_by_id_found(self) -> None:
        session = _mock_session()
        gate = ApprovalGate(id="gate-1", action_type="deploy", status="pending")
        session.get.return_value = gate

        repo = ApprovalGateRepository(session)
        result = await repo.get_by_id("gate-1")

        assert result is gate

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self) -> None:
        session = _mock_session()
        session.get.return_value = None

        repo = ApprovalGateRepository(session)
        result = await repo.get_by_id("gate-nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_pending(self) -> None:
        session = _mock_session()
        gates = [
            ApprovalGate(id="gate-1", action_type="deploy", status="pending"),
        ]
        session.execute.return_value = _mock_scalars(gates)

        repo = ApprovalGateRepository(session)
        result = await repo.get_pending()

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_pending_with_action_type(self) -> None:
        session = _mock_session()
        gates = [
            ApprovalGate(id="gate-1", action_type="deploy", status="pending"),
        ]
        session.execute.return_value = _mock_scalars(gates)

        repo = ApprovalGateRepository(session)
        result = await repo.get_pending(action_type="deploy")

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_pending_empty(self) -> None:
        session = _mock_session()
        session.execute.return_value = _mock_scalars([])

        repo = ApprovalGateRepository(session)
        result = await repo.get_pending()

        assert result == []

    @pytest.mark.asyncio
    async def test_list_all(self) -> None:
        session = _mock_session()
        gates = [
            ApprovalGate(id="gate-1", action_type="deploy", status="pending"),
            ApprovalGate(id="gate-2", action_type="merge", status="approved"),
        ]
        session.execute.return_value = _mock_scalars(gates)

        repo = ApprovalGateRepository(session)
        result = await repo.list_all()

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_all_with_action_type_filter(self) -> None:
        session = _mock_session()
        gates = [
            ApprovalGate(id="gate-1", action_type="deploy", status="pending"),
        ]
        session.execute.return_value = _mock_scalars(gates)

        repo = ApprovalGateRepository(session)
        result = await repo.list_all(action_type="deploy")

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_by_resource(self) -> None:
        session = _mock_session()
        gates = [
            ApprovalGate(id="gate-1", action_type="deploy", status="pending", resource_id="res-1"),
        ]
        session.execute.return_value = _mock_scalars(gates)

        repo = ApprovalGateRepository(session)
        result = await repo.get_by_resource("res-1")

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_by_resource_empty(self) -> None:
        session = _mock_session()
        session.execute.return_value = _mock_scalars([])

        repo = ApprovalGateRepository(session)
        result = await repo.get_by_resource("res-nonexistent")

        assert result == []

    @pytest.mark.asyncio
    async def test_create(self) -> None:
        session = _mock_session()
        gate = ApprovalGate(id="gate-1", action_type="deploy", status="pending")

        repo = ApprovalGateRepository(session)
        result = await repo.create(gate)

        session.add.assert_called_once_with(gate)
        assert result is gate


# ── ApprovalVoteRepository ──────────────────────────────────────


class TestApprovalVoteRepository:
    @pytest.mark.asyncio
    async def test_get_by_gate(self) -> None:
        session = _mock_session()
        votes = [
            ApprovalVote(id="vote-1", gate_id="gate-1", voter="user-1", decision="approve"),
            ApprovalVote(id="vote-2", gate_id="gate-1", voter="user-2", decision="reject"),
        ]
        session.execute.return_value = _mock_scalars(votes)

        repo = ApprovalVoteRepository(session)
        result = await repo.get_by_gate("gate-1")

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_by_gate_empty(self) -> None:
        session = _mock_session()
        session.execute.return_value = _mock_scalars([])

        repo = ApprovalVoteRepository(session)
        result = await repo.get_by_gate("gate-nonexistent")

        assert result == []

    @pytest.mark.asyncio
    async def test_create(self) -> None:
        session = _mock_session()
        vote = ApprovalVote(id="vote-1", gate_id="gate-1", voter="user-1", decision="approve")

        repo = ApprovalVoteRepository(session)
        result = await repo.create(vote)

        session.add.assert_called_once_with(vote)
        assert result is vote

    @pytest.mark.asyncio
    async def test_get_by_id_found(self) -> None:
        session = _mock_session()
        vote = ApprovalVote(id="vote-1", gate_id="gate-1", voter="user-1", decision="approve")
        session.get.return_value = vote

        repo = ApprovalVoteRepository(session)
        result = await repo.get_by_id("vote-1")

        assert result is vote

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self) -> None:
        session = _mock_session()
        session.get.return_value = None

        repo = ApprovalVoteRepository(session)
        result = await repo.get_by_id("vote-nonexistent")

        assert result is None
