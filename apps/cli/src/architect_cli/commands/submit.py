"""ARCHITECT CLI — submit command implementation."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import typer

from architect_cli.output import console, print_error, print_success


def submit(
    spec_file: Path,
    gateway_url: str = "http://localhost:8000",
    dry_run: bool = False,
) -> None:
    """Submit a task specification (YAML/JSON) to ARCHITECT for execution."""
    if not spec_file.exists():
        print_error(f"File not found: {spec_file}")
        raise typer.Exit(code=1)

    suffix = spec_file.suffix.lower()
    raw_text = spec_file.read_text()

    if suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore[import-untyped]

            payload = yaml.safe_load(raw_text)
        except ImportError:
            print_error("PyYAML is required for YAML files. Install with: pip install pyyaml")
            raise typer.Exit(code=1) from None
    elif suffix == ".json":
        payload = json.loads(raw_text)
    else:
        print_error(f"Unsupported file format: {suffix}. Use .yaml, .yml, or .json")
        raise typer.Exit(code=1)

    if dry_run:
        console.print("[bold]Dry-run mode:[/bold] spec parsed successfully.")
        console.print_json(json.dumps(payload, indent=2, default=str))
        return

    try:
        with httpx.Client(base_url=gateway_url, timeout=30.0) as client:
            resp = client.post("/api/v1/tasks", json=payload)
            resp.raise_for_status()
            result = resp.json()

        task_id = result.get("task_id", "unknown")
        print_success(f"Task submitted successfully. ID: {task_id}")
        console.print(f"  Track progress: [bold]architect status {task_id}[/bold]")

    except httpx.HTTPStatusError as exc:
        print_error(f"HTTP {exc.response.status_code}: {exc.response.text}")
        raise typer.Exit(code=1) from None
    except httpx.ConnectError:
        print_error(f"Cannot connect to gateway at {gateway_url}")
        raise typer.Exit(code=1) from None
