"""Abstract base for sandbox executors."""

from __future__ import annotations

from abc import ABC, abstractmethod

from execution_sandbox.models import SandboxSession, SandboxSpec


class ExecutorBase(ABC):
    """Interface every sandbox executor must implement.

    Concrete implementations can back onto Docker, Firecracker, gVisor, etc.
    """

    @abstractmethod
    async def create(self, spec: SandboxSpec) -> SandboxSession:
        """Provision a new sandbox container from *spec* and return its session."""

    @abstractmethod
    async def execute_command(
        self, session_id: str, command: str, timeout: int = 60
    ) -> tuple[int, str, str]:
        """Run *command* inside the sandbox identified by *session_id*.

        Returns:
            A ``(exit_code, stdout, stderr)`` tuple.
        """

    @abstractmethod
    async def write_files(self, session_id: str, files: dict[str, str]) -> None:
        """Write *files* (path -> content mapping) into the sandbox."""

    @abstractmethod
    async def read_files(self, session_id: str, paths: list[str]) -> dict[str, str]:
        """Read files from the sandbox.

        Returns:
            A ``{path: content}`` mapping for each requested path.
        """

    @abstractmethod
    async def destroy(self, session_id: str) -> None:
        """Tear down the sandbox and release all resources."""

    @abstractmethod
    def get_session(self, session_id: str) -> SandboxSession | None:
        """Return the session for *session_id*, or ``None``."""

    @abstractmethod
    def active_session_count(self) -> int:
        """Return the number of currently active sessions."""
