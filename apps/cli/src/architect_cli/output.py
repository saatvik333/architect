"""ARCHITECT CLI — rich console output helpers."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.theme import Theme

# Custom theme for ARCHITECT CLI
architect_theme = Theme(
    {
        "info": "bold blue",
        "success": "bold green",
        "warning": "bold yellow",
        "error": "bold red",
        "heading": "bold cyan",
    }
)

console = Console(theme=architect_theme)


def print_success(message: str) -> None:
    """Print a success message with a green checkmark."""
    console.print(f"[success]OK[/success] {message}")


def print_error(message: str) -> None:
    """Print an error message with a red cross."""
    console.print(f"[error]ERROR[/error] {message}", style="error")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[warning]WARN[/warning] {message}")


def print_info(message: str) -> None:
    """Print an informational message."""
    console.print(f"[info]INFO[/info] {message}")


def print_header(title: str, subtitle: str | None = None) -> None:
    """Print a styled header panel."""
    content = f"[bold]{title}[/bold]"
    if subtitle:
        content += f"\n[dim]{subtitle}[/dim]"
    console.print(Panel(content, border_style="cyan", expand=False))


def print_key_value(key: str, value: str) -> None:
    """Print a key-value pair with consistent formatting."""
    console.print(f"  [bold cyan]{key}:[/bold cyan] {value}")


def print_table(headers: list[str], rows: list[list[str]], *, title: str | None = None) -> None:
    """Print a generic rich table."""
    from rich.table import Table

    table = Table(title=title, show_header=True)
    for h in headers:
        table.add_column(h)
    for row in rows:
        table.add_row(*row)
    console.print(table)


def print_json(data: object) -> None:
    """Pretty-print JSON with syntax highlighting."""
    import json

    from rich.syntax import Syntax

    formatted = json.dumps(data, indent=2, default=str)
    console.print(Syntax(formatted, "json", theme="monokai"))


def print_progress(task_id: str, progress: float, status: str) -> None:
    """Print a single-line progress indicator."""
    bar_len = 20
    filled = int(progress * bar_len)
    bar = f"[green]{'█' * filled}[/green]{'░' * (bar_len - filled)}"
    console.print(f"  {task_id}  {bar} {progress:.0%}  [{status}]")
