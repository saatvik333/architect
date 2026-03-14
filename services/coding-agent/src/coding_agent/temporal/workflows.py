"""Temporal workflow definitions for the Coding Agent."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from coding_agent.temporal.activities import (
        execute_in_sandbox,
        generate_code,
        plan_task,
    )


@workflow.defn
class CodingAgentWorkflow:
    """Temporal workflow that orchestrates the coding agent loop.

    Steps: plan -> generate -> test in sandbox -> (retry if needed) -> done.
    """

    @workflow.run
    async def run(self, run_data: dict[str, Any]) -> dict[str, Any]:
        """Execute the full coding agent pipeline.

        Args:
            run_data: Serialised :class:`AgentRun` dict containing
                spec_context, codebase_context, and config.

        Returns:
            A dict with ``files`` (list of generated file dicts),
            ``plan`` (the implementation plan), and ``test_result``
            from the final sandbox execution.
        """
        # Version gate: establishes baseline for future behavioral changes.
        workflow.patched("v1-coding-agent-baseline")

        max_retries = run_data.get("max_retries", 3)

        # Step 1: Plan
        plan = await workflow.execute_activity(
            plan_task,
            args=[run_data],
            start_to_close_timeout=timedelta(minutes=5),
        )

        # Step 2: Generate code
        files = await workflow.execute_activity(
            generate_code,
            args=[plan, run_data],
            start_to_close_timeout=timedelta(minutes=10),
        )

        # Step 3: Test in sandbox, retry if needed
        test_result: dict[str, Any] = {}
        for attempt in range(max_retries + 1):
            test_commands = [
                "cd /workspace && python -m py_compile $(find . -name '*.py') 2>&1",
                "cd /workspace && python -m pytest --tb=short -q 2>&1",
            ]

            test_result = await workflow.execute_activity(
                execute_in_sandbox,
                args=[files, test_commands],
                start_to_close_timeout=timedelta(minutes=10),
            )

            # Check if all commands passed
            all_passed = all(
                cr.get("exit_code", 1) == 0 for cr in test_result.get("command_results", [])
            )

            if all_passed:
                break

            # On failure, regenerate if retries remain
            if attempt < max_retries:
                files = await workflow.execute_activity(
                    generate_code,
                    args=[plan, run_data],
                    start_to_close_timeout=timedelta(minutes=10),
                )

        return {
            "plan": plan,
            "files": files,
            "test_result": test_result,
        }
