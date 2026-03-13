"""ARCHITECT CLI — main entry point."""

from __future__ import annotations

import typer

app = typer.Typer(
    name="architect",
    help="CLI for the ARCHITECT autonomous coding system.",
    no_args_is_help=True,
)


@app.command()
def submit(
    spec_file: str = typer.Argument(help="Path to a YAML or JSON task specification file"),
    gateway_url: str = typer.Option(
        "http://localhost:8000",
        "--gateway-url",
        envvar="ARCHITECT_GATEWAY_URL",
        help="API gateway base URL",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate the spec without submitting"),
) -> None:
    """Submit a task specification (YAML/JSON) to ARCHITECT for execution."""
    from pathlib import Path

    from architect_cli.commands.submit import submit as _submit

    _submit(Path(spec_file), gateway_url, dry_run)


@app.command()
def status(
    task_id: str = typer.Argument(help="Task or project ID to query"),
    gateway_url: str = typer.Option(
        "http://localhost:8000",
        "--gateway-url",
        envvar="ARCHITECT_GATEWAY_URL",
        help="API gateway base URL",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed status"),
) -> None:
    """Query the status of a task or project."""
    from architect_cli.commands.status import status as _status

    _status(task_id, gateway_url, verbose)


@app.command()
def logs(
    task_id: str = typer.Argument(help="Task ID to stream logs for"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output"),
    gateway_url: str = typer.Option(
        "http://localhost:8000",
        "--gateway-url",
        envvar="ARCHITECT_GATEWAY_URL",
        help="API gateway base URL",
    ),
) -> None:
    """Stream execution logs for a task."""
    import httpx

    from architect_cli.output import console, print_error

    try:
        with httpx.Client(base_url=gateway_url, timeout=30.0) as client:
            resp = client.get(f"/api/v1/tasks/{task_id}/logs", params={"follow": follow})
            resp.raise_for_status()
            data = resp.json()

        for entry in data.get("entries", []):
            ts = entry.get("timestamp", "")
            level = entry.get("level", "INFO")
            message = entry.get("message", "")
            console.print(f"[dim]{ts}[/dim] [{_level_color(level)}]{level:>5}[/] {message}")

        if not data.get("entries"):
            console.print("[dim]No log entries found.[/dim]")

    except httpx.HTTPStatusError as exc:
        print_error(f"HTTP {exc.response.status_code}: {exc.response.text}")
        raise typer.Exit(code=1) from None
    except httpx.ConnectError:
        print_error(f"Cannot connect to gateway at {gateway_url}")
        raise typer.Exit(code=1) from None


@app.command()
def health(
    gateway_url: str = typer.Option(
        "http://localhost:8000",
        "--gateway-url",
        envvar="ARCHITECT_GATEWAY_URL",
        help="API gateway base URL",
    ),
    all_services: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Check all individual services directly",
    ),
) -> None:
    """Check health of ARCHITECT services."""
    from architect_cli.commands.health import health as _health

    _health(gateway_url, all_services)


def _level_color(level: str) -> str:
    """Return a rich color string for the given log level."""
    colors: dict[str, str] = {
        "DEBUG": "dim",
        "INFO": "blue",
        "WARNING": "yellow",
        "ERROR": "red",
        "CRITICAL": "bold red",
    }
    return colors.get(level.upper(), "white")


if __name__ == "__main__":
    app()
