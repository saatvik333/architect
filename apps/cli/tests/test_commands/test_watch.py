"""Tests for the architect CLI watch command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from architect_cli.main import app

runner = CliRunner()


def _mock_client(responses: list[dict]) -> MagicMock:
    """Create a mock httpx client that returns successive responses."""
    mock_response = MagicMock()
    mock_response.json.side_effect = responses
    mock_response.raise_for_status = MagicMock()

    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.get.return_value = mock_response
    return client


class TestWatchCommand:
    @patch("architect_cli.commands.watch.time.sleep")
    @patch("architect_cli.commands.watch.httpx.Client")
    def test_watch_exits_on_completed(self, mock_cls: MagicMock, mock_sleep: MagicMock) -> None:
        client = _mock_client([{"status": "completed", "progress": 1.0}])
        mock_cls.return_value = client

        result = runner.invoke(app, ["watch", "task-123"])
        assert result.exit_code == 0
        assert "completed" in result.output.lower()

    @patch("architect_cli.commands.watch.time.sleep")
    @patch("architect_cli.commands.watch.httpx.Client")
    def test_watch_exits_on_failed(self, mock_cls: MagicMock, mock_sleep: MagicMock) -> None:
        client = _mock_client([{"status": "failed", "progress": 0.5}])
        mock_cls.return_value = client

        result = runner.invoke(app, ["watch", "task-123"])
        assert "failed" in result.output.lower()

    @patch("architect_cli.commands.watch.time.sleep")
    @patch("architect_cli.commands.watch.httpx.Client")
    def test_watch_polls_then_exits(self, mock_cls: MagicMock, mock_sleep: MagicMock) -> None:
        responses = [
            {"status": "running", "progress": 0.3},
            {"status": "running", "progress": 0.7},
            {"status": "completed", "progress": 1.0},
        ]
        mock_resp = MagicMock()
        mock_resp.json.side_effect = responses
        mock_resp.raise_for_status = MagicMock()

        client = MagicMock()
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        client.get.return_value = mock_resp
        mock_cls.return_value = client

        result = runner.invoke(app, ["watch", "task-123"])
        assert result.exit_code == 0
        assert mock_sleep.call_count == 2

    @patch("architect_cli.commands.watch.httpx.Client")
    def test_watch_connection_error(self, mock_cls: MagicMock) -> None:
        import httpx

        client = MagicMock()
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        client.get.side_effect = httpx.ConnectError("refused")
        mock_cls.return_value = client

        result = runner.invoke(app, ["watch", "task-123"])
        assert result.exit_code == 1
