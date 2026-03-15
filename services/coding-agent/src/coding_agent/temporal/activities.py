"""Temporal activity definitions for the Coding Agent."""

from __future__ import annotations

from typing import Any

import httpx
from temporalio import activity

from architect_common.logging import get_logger
from architect_llm.client import LLMClient
from architect_sandbox_client.client import SandboxClient
from architect_sandbox_client.models import ExecutionRequest
from coding_agent.coder import CodeGenerator
from coding_agent.config import CodingAgentConfig
from coding_agent.git import GitCommitError, GitCommitter
from coding_agent.models import (
    AgentConfig,
    CodebaseContext,
    GeneratedFile,
    SpecContext,
)
from coding_agent.planner import TaskPlanner

logger = get_logger(component="coding_agent.temporal.activities")


@activity.defn
async def plan_task(run_data: dict[str, Any]) -> str:
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
async def generate_code(plan: str, run_data: dict[str, Any]) -> list[dict[str, Any]]:
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
async def execute_in_sandbox(files: list[dict[str, Any]], commands: list[str]) -> dict[str, Any]:
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


@activity.defn
async def commit_code(
    files: list[dict[str, Any]],
    commit_message: str,
    repo_path: str,
) -> dict[str, Any]:
    """Commit generated code files to a git repository.

    Args:
        files: List of dicts with ``path`` and ``content`` keys.
        commit_message: The commit message.
        repo_path: Path to the git repository root.

    Returns:
        A dict with ``commit_hash`` and ``files_written`` count.
    """
    activity.logger.info(
        "commit_code activity started",
        extra={"file_count": len(files), "repo_path": repo_path},
    )

    generated_files = [GeneratedFile.model_validate(f) for f in files]
    committer = GitCommitter()

    try:
        commit_hash = await committer.commit(
            files=generated_files,
            message=commit_message,
            repo_path=repo_path,
        )
    except GitCommitError:
        logger.exception("commit_code failed")
        raise

    return {"commit_hash": commit_hash, "files_written": len(generated_files)}


@activity.defn
async def update_world_state(
    commit_hash: str,
    task_id: str,
    agent_id: str,
    wsl_base_url: str,
) -> dict[str, Any]:
    """Update the World State Ledger with a new commit hash.

    Args:
        commit_hash: The 40-char hex commit hash to record.
        task_id: The branded task identifier.
        agent_id: The branded agent identifier.
        wsl_base_url: Base URL of the World State Ledger service.

    Returns:
        A dict with ``proposal_id`` and ``accepted`` boolean.
    """
    activity.logger.info(
        "update_world_state activity started",
        extra={"commit_hash": commit_hash, "wsl_base_url": wsl_base_url},
    )

    try:
        async with httpx.AsyncClient(base_url=wsl_base_url, timeout=30.0) as client:
            # Read current state to get old commit hash
            state_resp = await client.get("/api/v1/state")
            state_resp.raise_for_status()
            state = state_resp.json()

            old_commit = None
            repo = state.get("repo")
            if repo is not None:
                old_commit = repo.get("commit_hash")

            # Submit a proposal to update repo.commit_hash
            proposal_payload = {
                "agent_id": agent_id,
                "task_id": task_id,
                "mutations": [
                    {
                        "path": "repo.commit_hash",
                        "old_value": old_commit,
                        "new_value": commit_hash,
                    },
                ],
                "rationale": f"Commit generated code for task {task_id}",
            }

            prop_resp = await client.post("/api/v1/proposals", json=proposal_payload)
            prop_resp.raise_for_status()
            proposal_id = prop_resp.json()["proposal_id"]

            # Validate and commit the proposal
            commit_resp = await client.post(f"/api/v1/proposals/{proposal_id}/commit")
            commit_resp.raise_for_status()
            accepted = commit_resp.json().get("accepted", False)

        logger.info(
            "world state updated",
            proposal_id=proposal_id,
            accepted=accepted,
        )

        return {"proposal_id": proposal_id, "accepted": accepted}

    except httpx.HTTPError:
        logger.exception(
            "failed to update world state (WSL may not be running)",
            commit_hash=commit_hash,
        )
        return {"proposal_id": "", "accepted": False}
