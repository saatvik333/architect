"""Tests for the architect CLI cancel command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from architect_cli.main import app

runner = CliRunner()


class TestCancelCommand:
    @patch("architect_cli.commands.cancel.httpx.Client")
    def test_cancel_success(self, mock_cls: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "cancelled"}
        mock_resp.raise_for_status = MagicMock()

        client = MagicMock()
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        client.post.return_value = mock_resp
        mock_cls.return_value = client

        result = runner.invoke(app, ["cancel", "task-123"])
        assert result.exit_code == 0
        assert "cancellation" in result.output.lower()

    @patch("architect_cli.commands.cancel.httpx.Client")
    def test_cancel_force_with_children(self, mock_cls: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "status": "cancelled",
            "cancelled_children": ["task-a", "task-b"],
        }
        mock_resp.raise_for_status = MagicMock()

        client = MagicMock()
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        client.post.return_value = mock_resp
        mock_cls.return_value = client

        result = runner.invoke(app, ["cancel", "task-123", "--force"])
        assert result.exit_code == 0
        assert "2" in result.output  # 2 children

    @patch("architect_cli.commands.cancel.httpx.Client")
    def test_cancel_connection_error(self, mock_cls: MagicMock) -> None:
        import httpx

        client = MagicMock()
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        client.post.side_effect = httpx.ConnectError("refused")
        mock_cls.return_value = client

        result = runner.invoke(app, ["cancel", "task-123"])
        assert result.exit_code == 1
