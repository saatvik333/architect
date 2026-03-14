"""ARCHITECT CLI — watch command implementation."""

from __future__ import annotations

import time
from typing import Any

import httpx
import typer
from rich.live import Live
from rich.table import Table

from architect_cli.output import console, print_error, print_success

_TERMINAL_STATES = {"completed", "failed", "cancelled"}


def watch(
    task_id: str,
    gateway_url: str = "http://localhost:8000",
    interval: float = 2.0,
) -> None:
    """Watch a task's progress with live updates."""
    try:
        with (
            httpx.Client(base_url=gateway_url, timeout=10.0) as client,
            Live(console=console, refresh_per_second=1) as live,
        ):
            start = time.monotonic()
            while True:
                resp = client.get(f"/api/v1/tasks/{task_id}")
                resp.raise_for_status()
                data = resp.json()

                elapsed = time.monotonic() - start
                table = _build_table(task_id, data, elapsed)
                live.update(table)

                status = data.get("status", "").lower()
                if status in _TERMINAL_STATES:
                    break
                time.sleep(interval)

        final_status = data.get("status", "unknown")
        if final_status == "completed":
            print_success(f"Task {task_id} completed.")
        else:
            print_error(f"Task {task_id} finished with status: {final_status}")

    except httpx.ConnectError:
        print_error(f"Cannot connect to gateway at {gateway_url}")
        raise typer.Exit(code=1) from None
    except httpx.HTTPStatusError as exc:
        print_error(f"HTTP {exc.response.status_code}: {exc.response.text}")
        raise typer.Exit(code=1) from None
    except KeyboardInterrupt:
        console.print("\n[dim]Watch stopped.[/dim]")


def _build_table(task_id: str, data: dict[str, Any], elapsed: float) -> Table:
    """Build a Rich table from task data."""
    table = Table(title=f"Watching: {task_id}", show_header=True)
    table.add_column("Field", style="bold cyan")
    table.add_column("Value")

    table.add_row("Status", data.get("status", "unknown"))
    progress = data.get("progress", 0.0)
    bar_len = 20
    filled = int(progress * bar_len)
    bar = f"[green]{'█' * filled}[/green]{'░' * (bar_len - filled)} {progress:.0%}"
    table.add_row("Progress", bar)

    children = data.get("children", [])
    if children:
        table.add_row("Children", str(len(children)))

    table.add_row("Elapsed", f"{elapsed:.1f}s")
    return table
