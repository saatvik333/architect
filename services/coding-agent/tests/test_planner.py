"""Tests for the TaskPlanner."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from architect_llm.models import LLMResponse
from coding_agent.models import CodebaseContext, SpecContext
from coding_agent.planner import TaskPlanner


class TestTaskPlanner:
    """Tests for :class:`TaskPlanner`."""

    @pytest.fixture
    def mock_llm(self) -> AsyncMock:
        client = AsyncMock()
        client.generate.return_value = LLMResponse(
            content=(
                "## Implementation Plan\n"
                "1. Create `src/greet.py` with `greet()` function\n"
                "2. Create `tests/test_greet.py` with unit tests\n"
                "3. Run pytest to verify\n"
            ),
            model_id="claude-sonnet-4-20250514",
            input_tokens=300,
            output_tokens=100,
            stop_reason="end_turn",
        )
        return client

    @pytest.fixture
    def planner(self, mock_llm: AsyncMock) -> TaskPlanner:
        return TaskPlanner(llm_client=mock_llm)

    async def test_plan_returns_string(
        self,
        planner: TaskPlanner,
    ) -> None:
        """Plan returns a non-empty markdown string."""
        spec = SpecContext(
            title="Add greeting function",
            description="Implement a greeting function.",
        )
        codebase = CodebaseContext()

        plan = await planner.plan(spec, codebase)

        assert isinstance(plan, str)
        assert len(plan) > 0
        assert "Implementation Plan" in plan

    async def test_plan_calls_llm(
        self,
        planner: TaskPlanner,
        mock_llm: AsyncMock,
    ) -> None:
        """Plan calls the LLM client exactly once."""
        spec = SpecContext(title="Test task")
        codebase = CodebaseContext()

        await planner.plan(spec, codebase)

        assert mock_llm.generate.call_count == 1

    async def test_plan_includes_task_info_in_prompt(
        self,
        planner: TaskPlanner,
        mock_llm: AsyncMock,
    ) -> None:
        """The LLM request includes the task title in the user message."""
        spec = SpecContext(
            title="Implement fibonacci",
            acceptance_criteria=["Must handle n=0 and n=1"],
        )
        codebase = CodebaseContext(
            relevant_files=["src/math_utils.py"],
        )

        await planner.plan(spec, codebase)

        call_args = mock_llm.generate.call_args
        request = call_args[0][0]
        user_content = request.messages[0]["content"]
        assert "Implement fibonacci" in user_content
        assert "math_utils.py" in user_content
