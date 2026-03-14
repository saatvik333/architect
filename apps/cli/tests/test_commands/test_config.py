"""Tests for the architect CLI config command."""

from __future__ import annotations

from unittest.mock import patch

from typer.testing import CliRunner

from architect_cli import config as cfg
from architect_cli.main import app

runner = CliRunner()


class TestConfigShow:
    def test_config_show_defaults(self) -> None:
        with patch.object(cfg, "_load_file", return_value={}):
            result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        assert "gateway_url" in result.output

    def test_config_show_file_values(self) -> None:
        with patch.object(cfg, "_load_file", return_value={"gateway_url": "http://custom:9000"}):
            result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        assert "custom" in result.output


class TestConfigSet:
    def test_config_set_valid_key(self) -> None:
        with patch.object(cfg, "set_value") as mock_set:
            result = runner.invoke(app, ["config", "set", "gateway_url", "http://new:8000"])
        assert result.exit_code == 0
        mock_set.assert_called_once_with("gateway_url", "http://new:8000")

    def test_config_set_invalid_key(self) -> None:
        result = runner.invoke(app, ["config", "set", "nonexistent", "val"])
        assert result.exit_code == 0  # prints error but doesn't crash
        assert "Unknown" in result.output or "ERROR" in result.output


class TestConfigReset:
    def test_config_reset(self) -> None:
        with patch.object(cfg, "reset") as mock_reset:
            result = runner.invoke(app, ["config", "reset"])
        assert result.exit_code == 0
        mock_reset.assert_called_once()


class TestConfigModule:
    def test_get_default(self) -> None:
        with (
            patch.object(cfg, "_load_file", return_value={}),
            patch.dict("os.environ", {}, clear=True),
        ):
            assert cfg.get("gateway_url") == "http://localhost:8000"

    def test_get_from_file(self) -> None:
        with (
            patch.object(cfg, "_load_file", return_value={"gateway_url": "http://file:9000"}),
            patch.dict("os.environ", {}, clear=True),
        ):
            assert cfg.get("gateway_url") == "http://file:9000"

    def test_get_env_overrides_file(self) -> None:
        with (
            patch.object(cfg, "_load_file", return_value={"gateway_url": "http://file:9000"}),
            patch.dict("os.environ", {"ARCHITECT_GATEWAY_URL": "http://env:7000"}),
        ):
            assert cfg.get("gateway_url") == "http://env:7000"

    def test_set_value_coerces_bool(self, tmp_path: object) -> None:
        saved: dict = {}
        with (
            patch.object(cfg, "_load_file", return_value={}),
            patch.object(cfg, "_save_file", side_effect=lambda d: saved.update(d)),
        ):
            cfg.set_value("color", "false")
        assert saved["color"] is False

    def test_set_value_coerces_int(self) -> None:
        saved: dict = {}
        with (
            patch.object(cfg, "_load_file", return_value={}),
            patch.object(cfg, "_save_file", side_effect=lambda d: saved.update(d)),
        ):
            cfg.set_value("default_timeout", "60")
        assert saved["default_timeout"] == 60

    def test_set_value_unknown_key_raises(self) -> None:
        import pytest

        with pytest.raises(KeyError, match="Unknown config key"):
            cfg.set_value("not_a_key", "val")
