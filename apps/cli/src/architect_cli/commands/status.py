"""ARCHITECT CLI — status command implementation."""

from __future__ import annotations

import httpx
import typer

from architect_cli.output import console, print_error


def status(
    task_id: str,
    gateway_url: str = "http://localhost:8000",
    verbose: bool = False,
) -> None:
    """Query the status of a task or project."""
    from rich.table import Table

    try:
        with httpx.Client(base_url=gateway_url, timeout=30.0) as client:
            resp = client.get(f"/api/v1/tasks/{task_id}")
            resp.raise_for_status()
            data = resp.json()

        table = Table(title=f"Task Status: {task_id}", show_header=True)
        table.add_column("Field", style="bold cyan")
        table.add_column("Value")

        table.add_row("ID", data.get("id", "N/A"))
        table.add_row("Status", _style_status(data.get("status", "unknown")))
        table.add_row("Created", data.get("created_at", "N/A"))
        table.add_row("Updated", data.get("updated_at", "N/A"))

        if verbose:
            table.add_row("Description", data.get("description", "N/A"))
            table.add_row("Assigned Agent", data.get("agent_id", "N/A"))

            subtasks = data.get("subtasks", [])
            if subtasks:
                table.add_row("Subtasks", str(len(subtasks)))
                for st in subtasks:
                    st_id = st.get("id", "?")
                    st_status = st.get("status", "unknown")
                    table.add_row(f"  - {st_id}", _style_status(st_status))

            if data.get("error"):
                table.add_row("Error", f"[red]{data['error']}[/red]")

        console.print(table)

    except httpx.HTTPStatusError as exc:
        print_error(f"HTTP {exc.response.status_code}: {exc.response.text}")
        raise typer.Exit(code=1) from None
    except httpx.ConnectError:
        print_error(f"Cannot connect to gateway at {gateway_url}")
        raise typer.Exit(code=1) from None


def _style_status(status_str: str) -> str:
    """Apply rich markup to a status string."""
    styles: dict[str, str] = {
        "pending": "[yellow]pending[/yellow]",
        "running": "[blue]running[/blue]",
        "completed": "[green]completed[/green]",
        "failed": "[red]failed[/red]",
        "cancelled": "[dim]cancelled[/dim]",
    }
    return styles.get(status_str.lower(), status_str)
