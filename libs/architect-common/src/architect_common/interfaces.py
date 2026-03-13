"""Protocol interfaces between ARCHITECT components.

Uses typing.Protocol for structural subtyping — no inheritance coupling.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from architect_common.enums import EvalVerdict, StatusEnum
from architect_common.types import AgentId, EventId, LedgerVersion, ProposalId, TaskId


@runtime_checkable
class WorldStateLedger(Protocol):
    async def get_current(self) -> dict[str, Any]: ...
    async def get_version(self, version: LedgerVersion) -> dict[str, Any]: ...
    async def submit_proposal(self, proposal: dict[str, Any]) -> ProposalId: ...
    async def validate_and_commit(self, proposal_id: ProposalId) -> bool: ...


@runtime_checkable
class TaskGraphEngine(Protocol):
    async def create_task(self, task: dict[str, Any]) -> TaskId: ...
    async def get_task(self, task_id: TaskId) -> dict[str, Any]: ...
    async def get_next_pending(self) -> dict[str, Any] | None: ...
    async def update_status(self, task_id: TaskId, status: StatusEnum) -> None: ...


@runtime_checkable
class SandboxManager(Protocol):
    async def create(self, spec: dict[str, Any]) -> str: ...
    async def execute_command(
        self, session_id: str, command: str, timeout_seconds: int = 60
    ) -> tuple[int, str, str]: ...
    async def destroy(self, session_id: str) -> None: ...


@runtime_checkable
class EvaluationEngine(Protocol):
    async def evaluate(self, task_id: TaskId, sandbox_session_id: str) -> dict[str, Any]: ...
    async def run_compilation_check(self, sandbox_session_id: str) -> EvalVerdict: ...
    async def run_unit_tests(self, sandbox_session_id: str) -> EvalVerdict: ...


@runtime_checkable
class CodingAgent(Protocol):
    async def execute(self, run: dict[str, Any]) -> dict[str, Any]: ...


@runtime_checkable
class EventLogger(Protocol):
    async def append(self, entry: dict[str, Any]) -> EventId: ...
    async def query(
        self,
        *,
        event_type: str | None = None,
        task_id: TaskId | None = None,
        agent_id: AgentId | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]: ...
