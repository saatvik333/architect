"""Mock implementations of Protocol interfaces from architect_common.interfaces.

These mocks are designed for unit tests: they store data in memory and
return canned responses, avoiding the need for real infrastructure.
"""

from __future__ import annotations

from typing import Any

from architect_common.enums import SandboxStatus
from architect_common.types import AgentId, EventId, TaskId, new_event_id


class MockEventLogger:
    """In-memory mock of the ``EventLogger`` protocol.

    Stores all appended events in a list and supports basic filtering.

    Usage::

        logger = MockEventLogger()
        event_id = await logger.append({"type": "task.created", ...})
        events = await logger.query(event_type="task.created")
    """

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def append(self, entry: dict[str, Any]) -> EventId:
        """Append an event and return a generated event ID."""
        event_id = new_event_id()
        entry_with_id = {**entry, "id": event_id}
        self.events.append(entry_with_id)
        return event_id

    async def query(
        self,
        *,
        event_type: str | None = None,
        task_id: TaskId | None = None,
        agent_id: AgentId | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query stored events with optional filters."""
        results = self.events

        if event_type is not None:
            results = [e for e in results if e.get("type") == event_type]

        if task_id is not None:
            results = [e for e in results if e.get("task_id") == task_id]

        if agent_id is not None:
            results = [e for e in results if e.get("agent_id") == agent_id]

        return results[:limit]

    def reset(self) -> None:
        """Clear all stored events."""
        self.events.clear()


class MockSandboxManager:
    """In-memory mock of the ``SandboxManager`` protocol.

    Returns canned execution results without actually creating containers.

    Usage::

        manager = MockSandboxManager()
        session_id = await manager.create({"image": "python:3.12"})
        exit_code, stdout, stderr = await manager.execute_command(session_id, "echo hi")
        await manager.destroy(session_id)
    """

    def __init__(self) -> None:
        self._session_counter: int = 0
        self.sessions: dict[str, dict[str, Any]] = {}
        self.commands_executed: list[dict[str, Any]] = []

        # Configurable canned responses: map command string to (exit_code, stdout, stderr)
        self.canned_responses: dict[str, tuple[int, str, str]] = {}

    async def create(self, spec: dict[str, Any]) -> str:
        """Create a mock sandbox session."""
        self._session_counter += 1
        session_id = f"mock-sandbox-{self._session_counter}"
        self.sessions[session_id] = {
            "id": session_id,
            "spec": spec,
            "status": SandboxStatus.READY,
        }
        return session_id

    async def execute_command(
        self, session_id: str, command: str, timeout_seconds: int = 60
    ) -> tuple[int, str, str]:
        """Execute a command in the mock sandbox.

        Returns the canned response for the command if configured,
        otherwise returns a successful empty result.
        """
        record = {
            "session_id": session_id,
            "command": command,
            "timeout_seconds": timeout_seconds,
        }
        self.commands_executed.append(record)

        if session_id in self.sessions:
            self.sessions[session_id]["status"] = SandboxStatus.RUNNING

        if command in self.canned_responses:
            return self.canned_responses[command]

        # Default: success with no output
        return (0, "", "")

    async def destroy(self, session_id: str) -> None:
        """Destroy a mock sandbox session."""
        if session_id in self.sessions:
            self.sessions[session_id]["status"] = SandboxStatus.DESTROYED

    def reset(self) -> None:
        """Clear all sessions and command history."""
        self._session_counter = 0
        self.sessions.clear()
        self.commands_executed.clear()
        self.canned_responses.clear()
