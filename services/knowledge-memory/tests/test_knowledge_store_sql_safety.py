"""Tests verifying SQL safety of KnowledgeStore methods.

Ensures that SQL queries use parameterized CASE expressions instead of
f-string column interpolation, eliminating SQL injection risks.
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from architect_common.types import HeuristicId
from knowledge_memory.knowledge_store import KnowledgeStore


class TestUpdateHeuristicOutcomeSQLSafety:
    """Verify update_heuristic_outcome uses parameterized SQL, not f-strings."""

    def test_no_fstring_column_interpolation_in_source(self) -> None:
        """The method source must not use f-string SQL with column variables."""
        source = inspect.getsource(KnowledgeStore.update_heuristic_outcome)
        # Should not contain f-string markers wrapping SQL
        assert 'f"""' not in source, "Method must not use f-string SQL"
        assert "f'''" not in source, "Method must not use f-string SQL"
        assert 'f"' not in source, "Method must not use f-string SQL"

    def test_uses_case_expressions_for_counters(self) -> None:
        """The SQL must use CASE WHEN :is_success for both counters."""
        source = inspect.getsource(KnowledgeStore.update_heuristic_outcome)
        assert "success_count = success_count + CASE WHEN :is_success" in source
        assert "failure_count = failure_count + CASE WHEN :is_success" in source

    def test_no_col_variable(self) -> None:
        """The method must not define a 'col' variable for column selection."""
        source = inspect.getsource(KnowledgeStore.update_heuristic_outcome)
        assert "col =" not in source, "Method must not use a col variable"
        assert "{col}" not in source, "Method must not interpolate col"

    @pytest.mark.asyncio
    async def test_success_true_passes_is_success_param(self) -> None:
        """When success=True, the bind parameter is_success should be True."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        session_factory = MagicMock()
        session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        store = KnowledgeStore(session_factory=session_factory)
        heuristic_id = HeuristicId("heur_test123")

        await store.update_heuristic_outcome(heuristic_id, success=True)

        mock_session.execute.assert_called_once()
        _, kwargs = mock_session.execute.call_args
        if not kwargs:
            args = mock_session.execute.call_args[0]
            params = args[1]
        else:
            params = kwargs.get("params", mock_session.execute.call_args[0][1])

        assert params["is_success"] is True
        assert params["id"] == str(heuristic_id)
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_success_false_passes_is_success_param(self) -> None:
        """When success=False, the bind parameter is_success should be False."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        session_factory = MagicMock()
        session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        store = KnowledgeStore(session_factory=session_factory)
        heuristic_id = HeuristicId("heur_test456")

        await store.update_heuristic_outcome(heuristic_id, success=False)

        mock_session.execute.assert_called_once()
        args = mock_session.execute.call_args[0]
        params = args[1]

        assert params["is_success"] is False
        assert params["id"] == str(heuristic_id)
        mock_session.commit.assert_called_once()
