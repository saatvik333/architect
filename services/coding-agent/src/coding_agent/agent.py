"""Core coding agent loop: plan -> generate -> test -> iterate."""

from __future__ import annotations

from typing import TYPE_CHECKING

from architect_common.enums import EventType
from architect_common.logging import get_logger
from architect_events.schemas import AgentCompletedEvent, EventEnvelope
from architect_sandbox_client.models import ExecutionRequest, ExecutionResult
from coding_agent.coder import CodeGenerator
from coding_agent.models import (
    AgentConfig,
    AgentOutput,
    AgentRun,
    GeneratedFile,
)
from coding_agent.planner import TaskPlanner

if TYPE_CHECKING:
    from architect_events.publisher import EventPublisher
    from architect_llm.client import LLMClient
    from architect_sandbox_client.client import SandboxClient

logger = get_logger(component="coding_agent.agent")


class CodingAgentLoop:
    """Orchestrates the full coding agent lifecycle.

    The agent loop follows these steps:
    1. Plan the implementation approach via LLM
    2. Generate code files via LLM
    3. Write files to sandbox
    4. Run tests in sandbox
    5. If tests fail and retries remain, fix and iterate
    6. Return final output
    """

    def __init__(
        self,
        llm_client: LLMClient,
        sandbox_client: SandboxClient,
        event_publisher: EventPublisher,
        config: AgentConfig | None = None,
        *,
        max_retries: int = 3,
    ) -> None:
        self._llm = llm_client
        self._sandbox = sandbox_client
        self._event_publisher = event_publisher
        self._config = config or AgentConfig()
        self._max_retries = max_retries

        self._planner = TaskPlanner(llm_client)
        self._coder = CodeGenerator(llm_client)

    async def execute(self, run: AgentRun) -> AgentOutput:
        """Execute the full agent loop for a given run.

        Args:
            run: The agent run containing task spec, codebase context, and config.

        Returns:
            An :class:`AgentOutput` with the generated files and metadata.

        Raises:
            Exception: Re-raises any unhandled errors after logging.
        """
        config = run.config or self._config

        logger.info(
            "agent loop started",
            agent_id=str(run.id),
            task_id=str(run.task_id),
        )

        total_tokens = 0

        try:
            # Step 1: Plan
            plan = await self._planner.plan(run.spec_context, run.codebase_context)
            total_tokens += self._llm.total_usage.total_tokens

            # Step 2: Generate initial code
            files = await self._coder.generate(
                plan=plan,
                spec=run.spec_context,
                codebase=run.codebase_context,
                config=config,
            )
            total_tokens = self._llm.total_usage.total_tokens

            # Step 3-5: Write to sandbox, test, iterate
            for attempt in range(self._max_retries + 1):
                logger.info(
                    "sandbox execution attempt",
                    attempt=attempt + 1,
                    max_retries=self._max_retries,
                    file_count=len(files),
                )

                # Write files to sandbox
                file_map = {f.path: f.content for f in files}
                exec_request = ExecutionRequest(
                    task_id=run.task_id,
                    agent_id=run.id,
                    files=file_map,
                    commands=[
                        "cd /workspace && python -m py_compile $(find . -name '*.py') 2>&1",
                        "cd /workspace && python -m pytest --tb=short -q 2>&1",
                    ],
                    timeout_seconds=300,
                )
                result = await self._sandbox.execute(exec_request)

                # Check results
                errors = self._collect_errors(result)

                if not errors:
                    logger.info(
                        "tests passed",
                        attempt=attempt + 1,
                    )
                    break

                logger.warning(
                    "tests failed",
                    attempt=attempt + 1,
                    error_count=len(errors),
                )

                if attempt < self._max_retries:
                    # Fix and retry
                    files = await self._coder.fix_errors(
                        files=files,
                        errors=errors,
                        spec=run.spec_context,
                    )
                    total_tokens = self._llm.total_usage.total_tokens

            # Build the commit message
            commit_message = self._build_commit_message(run, files)

            output = AgentOutput(
                task_id=run.task_id,
                agent_id=run.id,
                files=files,
                commit_message=commit_message,
                reasoning_summary=plan[:500],
                tokens_used=total_tokens,
                model_id=config.model_id,
            )

            # Publish completion event
            await self._publish_completed(run, total_tokens)

            logger.info(
                "agent loop completed",
                agent_id=str(run.id),
                task_id=str(run.task_id),
                files_produced=len(files),
                tokens_used=total_tokens,
            )

            return output

        except Exception:
            logger.exception(
                "agent loop failed",
                agent_id=str(run.id),
                task_id=str(run.task_id),
            )
            raise

    @staticmethod
    def _collect_errors(result: ExecutionResult) -> list[str]:
        """Extract error messages from sandbox execution results."""
        errors: list[str] = []
        for cmd_result in result.command_results:
            if cmd_result.exit_code != 0:
                output = cmd_result.stderr or cmd_result.stdout
                for line in output.splitlines():
                    stripped = line.strip()
                    if stripped and (
                        "Error" in stripped or "FAILED" in stripped or "error" in stripped.lower()
                    ):
                        errors.append(stripped)
                # If no specific error lines found, add generic message
                if not errors and output.strip():
                    errors.append(f"Command failed (exit {cmd_result.exit_code}): {output[:500]}")
        return errors

    @staticmethod
    def _build_commit_message(run: AgentRun, files: list[GeneratedFile]) -> str:
        """Build a commit message summarising the agent's work."""
        file_count = len(files)
        test_count = sum(1 for f in files if f.is_test)
        src_count = file_count - test_count

        return (
            f"feat: implement {run.spec_context.title}\n"
            f"\n"
            f"Generated {src_count} source file(s) and {test_count} test file(s)\n"
            f"Task: {run.task_id}\n"
            f"Agent: {run.id}"
        )

    async def _publish_completed(self, run: AgentRun, tokens: int) -> None:
        """Publish an agent.completed event."""
        payload = AgentCompletedEvent(
            agent_id=run.id,
            tokens_consumed=tokens,
        )
        envelope = EventEnvelope(
            type=EventType.AGENT_COMPLETED,
            payload=payload.model_dump(),
        )
        await self._event_publisher.publish(envelope)
