"""ARCHITECT CLI — configuration management."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_CONFIG_DIR = Path(os.environ.get("ARCHITECT_CONFIG_DIR", "~/.config/architect")).expanduser()
_CONFIG_FILE = _CONFIG_DIR / "config.json"

_DEFAULTS: dict[str, Any] = {
    "gateway_url": "http://localhost:8000",
    "default_timeout": 30,
    "output_format": "table",
    "color": True,
}

_ENV_MAP: dict[str, str] = {
    "gateway_url": "ARCHITECT_GATEWAY_URL",
    "default_timeout": "ARCHITECT_DEFAULT_TIMEOUT",
    "output_format": "ARCHITECT_OUTPUT_FORMAT",
    "color": "ARCHITECT_COLOR",
}


def _load_file() -> dict[str, Any]:
    """Load config from disk, returning empty dict if missing."""
    if _CONFIG_FILE.exists():
        return json.loads(_CONFIG_FILE.read_text())  # type: ignore[no-any-return]
    return {}


def _save_file(data: dict[str, Any]) -> None:
    """Persist config to disk."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE.write_text(json.dumps(data, indent=2) + "\n")


def get(key: str) -> Any:
    """Resolve a config value: env var > file > default."""
    env_var = _ENV_MAP.get(key)
    if env_var and (val := os.environ.get(env_var)):
        return val
    file_data = _load_file()
    if key in file_data:
        return file_data[key]
    return _DEFAULTS.get(key)


def get_all() -> dict[str, Any]:
    """Return the fully resolved config dict."""
    return {k: get(k) for k in _DEFAULTS}


def set_value(key: str, value: str) -> None:
    """Set a config key in the file."""
    if key not in _DEFAULTS:
        msg = f"Unknown config key: {key}. Valid keys: {', '.join(sorted(_DEFAULTS))}"
        raise KeyError(msg)
    file_data = _load_file()
    # Coerce types to match defaults
    default = _DEFAULTS[key]
    if isinstance(default, bool):
        file_data[key] = value.lower() in ("true", "1", "yes")
    elif isinstance(default, int):
        file_data[key] = int(value)
    else:
        file_data[key] = value
    _save_file(file_data)


def reset() -> None:
    """Delete the config file, restoring defaults."""
    if _CONFIG_FILE.exists():
        _CONFIG_FILE.unlink()
