"""ARCHITECT CLI — state command implementation."""

from __future__ import annotations

import json
from typing import Any

import httpx
import typer
from rich.syntax import Syntax

from architect_cli.output import console, print_error


def state_show(
    gateway_url: str = "http://localhost:8000",
    path: str | None = None,
) -> None:
    """Show world state, optionally filtered by dot-path."""
    try:
        with httpx.Client(base_url=gateway_url, timeout=30.0) as client:
            resp = client.get("/api/v1/state")
            resp.raise_for_status()
            data = resp.json()

        # Drill into nested dict if path given
        display = data
        if path:
            display = _resolve_path(data, path)

        formatted = json.dumps(display, indent=2, default=str)
        console.print(Syntax(formatted, "json", theme="monokai"))

    except httpx.HTTPStatusError as exc:
        print_error(f"HTTP {exc.response.status_code}: {exc.response.text}")
        raise typer.Exit(code=1) from None
    except httpx.ConnectError:
        print_error(f"Cannot connect to gateway at {gateway_url}")
        raise typer.Exit(code=1) from None
    except KeyError as exc:
        print_error(f"Path not found: {exc}")
        raise typer.Exit(code=1) from None


def _resolve_path(data: Any, path: str) -> Any:
    """Walk a dot-separated path into a nested dict."""
    current = data
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                msg = part
                raise KeyError(msg)
            current = current[part]
        else:
            msg = part
            raise KeyError(msg)
    return current
