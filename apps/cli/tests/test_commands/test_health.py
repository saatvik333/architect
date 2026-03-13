"""Tests for the architect CLI health command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from architect_cli.main import app

runner = CliRunner()


class TestHealthCommand:
    """Tests for the health check CLI command."""

    @patch("architect_cli.commands.health.httpx.Client")
    def test_health_gateway_healthy(self, mock_client_cls: MagicMock) -> None:
        """Health command reports success when gateway returns healthy."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "healthy",
            "services": {
                "task-graph-engine": {"status": "healthy", "latency_ms": 12},
                "execution-sandbox": {"status": "healthy", "latency_ms": 8},
            },
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        result = runner.invoke(app, ["health"])
        assert result.exit_code == 0
        assert "OK" in result.output or "operational" in result.output.lower()

    @patch("architect_cli.commands.health.httpx.Client")
    def test_health_gateway_unreachable(self, mock_client_cls: MagicMock) -> None:
        """Health command exits with error when gateway is unreachable."""
        import httpx

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")
        mock_client_cls.return_value = mock_client

        result = runner.invoke(app, ["health"])
        assert result.exit_code == 1

    def test_health_no_args_is_valid(self) -> None:
        """Health command should be callable without arguments (uses defaults)."""
        # Just verify the command exists and is registered
        result = runner.invoke(app, ["health", "--help"])
        assert result.exit_code == 0
        assert "health" in result.output.lower()
