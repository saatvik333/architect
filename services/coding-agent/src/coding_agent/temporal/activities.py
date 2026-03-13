"""Temporal activity definitions for the Coding Agent."""

from __future__ import annotations

from temporalio import activity

from architect_common.logging import get_logger
from architect_llm.client import LLMClient
from architect_sandbox_client.client import SandboxClient
from architect_sandbox_client.models import ExecutionRequest
from coding_agent.coder import CodeGenerator
from coding_agent.config import CodingAgentConfig
from coding_agent.models import (
    AgentConfig,
    CodebaseContext,
    SpecContext,
)
from coding_agent.planner import TaskPlanner

logger = get_logger(component="coding_agent.temporal.activities")


@activity.defn
async def plan_task(run_data: dict) -> str:
    """Generate an implementation plan for a task.

    Args:
        run_data: Serialised :class:`AgentRun` dict.

    Returns:
        The implementation plan as a markdown string.
    """
    activity.logger.info("plan_task activity started")

    config = CodingAgentConfig()
    llm_client = LLMClient(
        api_key=config.architect.claude.api_key.get_secret_value(),
        default_model=config.default_model_id,
    )

    try:
        planner = TaskPlanner(llm_client)

        spec = SpecContext.model_validate(run_data.get("spec_context", {}))
        codebase = CodebaseContext.model_validate(run_data.get("codebase_context", {}))

        plan = await planner.plan(spec, codebase)
        return plan
    finally:
        await llm_client.close()


@activity.defn
async def generate_code(plan: str, run_data: dict) -> list[dict]:
    """Generate code files from a plan and task specification.

    Args:
        plan: The implementation plan.
        run_data: Serialised :class:`AgentRun` dict.

    Returns:
        A list of serialised :class:`GeneratedFile` dicts.
    """
    activity.logger.info("generate_code activity started")

    config = CodingAgentConfig()
    llm_client = LLMClient(
        api_key=config.architect.claude.api_key.get_secret_value(),
        default_model=config.default_model_id,
    )

    try:
        coder = CodeGenerator(llm_client)

        spec = SpecContext.model_validate(run_data.get("spec_context", {}))
        codebase = CodebaseContext.model_validate(run_data.get("codebase_context", {}))
        agent_config = AgentConfig.model_validate(run_data.get("config", {}))

        files = await coder.generate(
            plan=plan,
            spec=spec,
            codebase=codebase,
            config=agent_config,
        )

        return [f.model_dump(mode="json") for f in files]
    finally:
        await llm_client.close()


@activity.defn
async def execute_in_sandbox(files: list[dict], commands: list[str]) -> dict:
    """Write files to a sandbox and execute commands.

    Args:
        files: List of dicts with ``path`` and ``content`` keys.
        commands: Shell commands to execute sequentially.

    Returns:
        A serialised :class:`ExecutionResult` dict.
    """
    activity.logger.info(
        "execute_in_sandbox activity started",
        extra={"file_count": len(files), "command_count": len(commands)},
    )

    config = CodingAgentConfig()
    sandbox_client = SandboxClient(base_url=config.sandbox_base_url)

    try:
        file_map = {f["path"]: f["content"] for f in files}

        request = ExecutionRequest(
            task_id="task-temporal00000",
            agent_id="agent-temporal0000",
            files=file_map,
            commands=commands,
            timeout_seconds=300,
        )

        result = await sandbox_client.execute(request)
        return result.model_dump(mode="json")
    finally:
        await sandbox_client.close()
