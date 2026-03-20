"""Tests for DockerExecutor initialization."""

from unittest.mock import MagicMock, patch


class TestDockerExecutorInit:
    @patch("execution_sandbox.docker_executor.docker.DockerClient")
    def test_default_unix_socket(self, mock_docker: MagicMock) -> None:
        from execution_sandbox.docker_executor import DockerExecutor

        DockerExecutor()
        mock_docker.assert_called_once_with(base_url="unix:///var/run/docker.sock")

    @patch("execution_sandbox.docker_executor.docker.DockerClient")
    def test_custom_docker_host(self, mock_docker: MagicMock) -> None:
        from execution_sandbox.docker_executor import DockerExecutor

        DockerExecutor(docker_host="tcp://proxy:2375")
        mock_docker.assert_called_once_with(base_url="tcp://proxy:2375")

    @patch("execution_sandbox.docker_executor.docker.DockerClient")
    def test_docker_host_overrides_socket(self, mock_docker: MagicMock) -> None:
        from execution_sandbox.docker_executor import DockerExecutor

        DockerExecutor(docker_socket="/custom/socket.sock", docker_host="tcp://proxy:2375")
        mock_docker.assert_called_once_with(base_url="tcp://proxy:2375")
