"""Tests for the architect CLI state command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from architect_cli.commands.state import _resolve_path
from architect_cli.main import app

runner = CliRunner()


class TestStateCommand:
    @patch("architect_cli.commands.state.httpx.Client")
    def test_state_show(self, mock_cls: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"version": 1, "data": {"files": {}}}
        mock_resp.raise_for_status = MagicMock()

        client = MagicMock()
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        client.get.return_value = mock_resp
        mock_cls.return_value = client

        result = runner.invoke(app, ["state"])
        assert result.exit_code == 0

    @patch("architect_cli.commands.state.httpx.Client")
    def test_state_with_path(self, mock_cls: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"nested": {"key": "value"}}}
        mock_resp.raise_for_status = MagicMock()

        client = MagicMock()
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        client.get.return_value = mock_resp
        mock_cls.return_value = client

        result = runner.invoke(app, ["state", "--path", "data.nested"])
        assert result.exit_code == 0

    @patch("architect_cli.commands.state.httpx.Client")
    def test_state_connection_error(self, mock_cls: MagicMock) -> None:
        import httpx

        client = MagicMock()
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        client.get.side_effect = httpx.ConnectError("refused")
        mock_cls.return_value = client

        result = runner.invoke(app, ["state"])
        assert result.exit_code == 1


class TestResolvePath:
    def test_simple_path(self) -> None:
        data = {"a": {"b": "c"}}
        assert _resolve_path(data, "a.b") == "c"

    def test_nested_dict(self) -> None:
        data = {"x": {"y": {"z": 42}}}
        assert _resolve_path(data, "x.y.z") == 42

    def test_missing_key_raises(self) -> None:
        data = {"a": 1}
        with pytest.raises(KeyError):
            _resolve_path(data, "b")

    def test_non_dict_intermediate_raises(self) -> None:
        data = {"a": "string"}
        with pytest.raises(KeyError):
            _resolve_path(data, "a.b")
