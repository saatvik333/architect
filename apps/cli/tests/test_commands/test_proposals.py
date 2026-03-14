"""Tests for the architect CLI proposals command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from architect_cli.main import app

runner = CliRunner()


def _mock_get_client(response_data: object) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.json.return_value = response_data
    mock_resp.raise_for_status = MagicMock()

    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.get.return_value = mock_resp
    return client


class TestProposalsList:
    @patch("architect_cli.commands.proposals.httpx.Client")
    def test_list_proposals(self, mock_cls: MagicMock) -> None:
        mock_cls.return_value = _mock_get_client(
            [
                {
                    "proposal_id": "prop-1",
                    "agent_id": "agent-a",
                    "verdict": "approved",
                    "created_at": "2026-01-01T00:00:00Z",
                },
            ]
        )

        result = runner.invoke(app, ["proposals", "list", "task-123"])
        assert result.exit_code == 0
        assert "prop-1" in result.output

    @patch("architect_cli.commands.proposals.httpx.Client")
    def test_list_empty(self, mock_cls: MagicMock) -> None:
        mock_cls.return_value = _mock_get_client([])

        result = runner.invoke(app, ["proposals", "list", "task-123"])
        assert result.exit_code == 0
        assert "No proposals" in result.output


class TestProposalsInspect:
    @patch("architect_cli.commands.proposals.httpx.Client")
    def test_inspect_proposal(self, mock_cls: MagicMock) -> None:
        mock_cls.return_value = _mock_get_client(
            {
                "proposal_id": "prop-1",
                "task_id": "task-123",
                "agent_id": "agent-a",
                "verdict": "approved",
                "created_at": "2026-01-01T00:00:00Z",
                "mutations": [{"path": "files.main_py", "value": "print('hello')"}],
            }
        )

        result = runner.invoke(app, ["proposals", "inspect", "prop-1"])
        assert result.exit_code == 0
        assert "prop-1" in result.output

    @patch("architect_cli.commands.proposals.httpx.Client")
    def test_inspect_connection_error(self, mock_cls: MagicMock) -> None:
        import httpx

        client = MagicMock()
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        client.get.side_effect = httpx.ConnectError("refused")
        mock_cls.return_value = client

        result = runner.invoke(app, ["proposals", "inspect", "prop-1"])
        assert result.exit_code == 1
