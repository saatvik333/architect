"""FastAPI dependency injection for the Execution Sandbox."""

from __future__ import annotations

from functools import lru_cache

from architect_common.logging import get_logger
from execution_sandbox.config import ExecutionSandboxConfig
from execution_sandbox.executor_base import ExecutorBase
from execution_sandbox.file_manager import FileManager

logger = get_logger(component="sandbox_dependencies")


@lru_cache(maxsize=1)
def get_config() -> ExecutionSandboxConfig:
    """Return the singleton service configuration."""
    return ExecutionSandboxConfig()


_executor: ExecutorBase | None = None
_file_manager: FileManager | None = None


def _create_executor(config: ExecutionSandboxConfig) -> ExecutorBase:
    """Create the appropriate executor based on configuration."""
    backend = config.executor_backend

    if backend == "auto":
        from execution_sandbox.kvm_check import is_firecracker_available, is_kvm_available

        if is_kvm_available() and is_firecracker_available(config.firecracker_binary):
            backend = "firecracker"
        else:
            backend = "docker"
            logger.info("firecracker_unavailable_falling_back_to_docker")

    if backend == "firecracker":
        from execution_sandbox.firecracker_executor import FirecrackerExecutor

        logger.info("using_firecracker_executor")
        return FirecrackerExecutor(config=config)

    from execution_sandbox.docker_executor import DockerExecutor

    logger.info("using_docker_executor")
    return DockerExecutor(docker_socket=config.docker_socket)


def get_executor() -> ExecutorBase:
    """Return the singleton sandbox executor.

    The executor type is determined by the ``executor_backend`` config:
    - ``"docker"``: Always use Docker containers.
    - ``"firecracker"``: Always use Firecracker microVMs (fails if KVM unavailable).
    - ``"auto"``: Try Firecracker, fall back to Docker.
    """
    global _executor
    if _executor is None:
        config = get_config()
        _executor = _create_executor(config)
    return _executor


def get_file_manager() -> FileManager:
    """Return the singleton :class:`FileManager`."""
    global _file_manager
    if _file_manager is None:
        config = get_config()
        _file_manager = FileManager(workspace_root=config.workspace_root)
    return _file_manager
