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
