"""FastAPI dependency injection for the Execution Sandbox."""

from __future__ import annotations

from functools import lru_cache

from execution_sandbox.config import ExecutionSandboxConfig
from execution_sandbox.docker_executor import DockerExecutor
from execution_sandbox.file_manager import FileManager


@lru_cache(maxsize=1)
def get_config() -> ExecutionSandboxConfig:
    """Return the singleton service configuration."""
    return ExecutionSandboxConfig()


_executor: DockerExecutor | None = None
_file_manager: FileManager | None = None


def get_executor() -> DockerExecutor:
    """Return the singleton :class:`DockerExecutor`."""
    global _executor
    if _executor is None:
        config = get_config()
        _executor = DockerExecutor(docker_socket=config.docker_socket)
    return _executor


def get_file_manager() -> FileManager:
    """Return the singleton :class:`FileManager`."""
    global _file_manager
    if _file_manager is None:
        config = get_config()
        _file_manager = FileManager(workspace_root=config.workspace_root)
    return _file_manager
