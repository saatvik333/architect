"""ARCHITECT CLI — config command implementation."""

from __future__ import annotations

from rich.table import Table

from architect_cli import config as cfg
from architect_cli.output import console, print_error, print_success


def config_show() -> None:
    """Display current configuration."""
    table = Table(title="ARCHITECT CLI Configuration", show_header=True)
    table.add_column("Key", style="bold cyan")
    table.add_column("Value")
    table.add_column("Source", style="dim")

    import os

    for key, value in cfg.get_all().items():
        env_var = cfg._ENV_MAP.get(key, "")
        if env_var and os.environ.get(env_var):
            source = f"env ({env_var})"
        elif key in cfg._load_file():
            source = "config file"
        else:
            source = "default"
        table.add_row(key, str(value), source)

    console.print(table)


def config_set(key: str, value: str) -> None:
    """Set a configuration value."""
    try:
        cfg.set_value(key, value)
        print_success(f"Set {key} = {value}")
    except KeyError as exc:
        print_error(str(exc))


def config_reset() -> None:
    """Reset configuration to defaults."""
    cfg.reset()
    print_success("Configuration reset to defaults.")
