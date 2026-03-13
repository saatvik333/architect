"""ARCHITECT CLI — health check command implementation."""

from __future__ import annotations

import httpx
import typer

from architect_cli.output import console, print_error, print_success

# Default services to check for health
DEFAULT_SERVICES: dict[str, str] = {
    "api-gateway": "http://localhost:8000",
    "task-graph-engine": "http://localhost:8001",
    "execution-sandbox": "http://localhost:8002",
    "world-state-ledger": "http://localhost:8003",
    "spec-engine": "http://localhost:8004",
    "multi-model-router": "http://localhost:8005",
    "codebase-comprehension": "http://localhost:8006",
    "agent-comm-bus": "http://localhost:8007",
}


def health(
    gateway_url: str = "http://localhost:8000",
    all_services: bool = False,
) -> None:
    """Check health of ARCHITECT services."""
    from rich.table import Table

    if all_services:
        _check_all_services()
        return

    # Default: check via the gateway aggregate endpoint
    try:
        with httpx.Client(base_url=gateway_url, timeout=10.0) as client:
            resp = client.get("/health")
            resp.raise_for_status()
            data = resp.json()

        overall = data.get("status", "unknown")
        if overall == "healthy":
            print_success("All systems operational.")
        else:
            print_error(f"System status: {overall}")

        services = data.get("services", {})
        if services:
            table = Table(title="Service Health", show_header=True)
            table.add_column("Service", style="bold")
            table.add_column("Status")
            table.add_column("Latency")

            for name, info in services.items():
                svc_status = info.get("status", "unknown")
                latency = info.get("latency_ms", "N/A")
                status_style = (
                    "[green]healthy[/green]"
                    if svc_status == "healthy"
                    else f"[red]{svc_status}[/red]"
                )
                table.add_row(name, status_style, f"{latency}ms" if latency != "N/A" else "N/A")

            console.print(table)

    except httpx.ConnectError:
        print_error(f"Cannot connect to gateway at {gateway_url}")
        raise typer.Exit(code=1) from None
    except httpx.HTTPStatusError as exc:
        print_error(f"HTTP {exc.response.status_code}: {exc.response.text}")
        raise typer.Exit(code=1) from None


def _check_all_services() -> None:
    """Check each service individually by hitting its /health endpoint."""
    from rich.table import Table

    table = Table(title="Direct Service Health Check", show_header=True)
    table.add_column("Service", style="bold")
    table.add_column("URL", style="dim")
    table.add_column("Status")

    healthy_count = 0
    total = len(DEFAULT_SERVICES)

    for name, url in DEFAULT_SERVICES.items():
        try:
            with httpx.Client(base_url=url, timeout=5.0) as client:
                resp = client.get("/health")
                resp.raise_for_status()
            table.add_row(name, url, "[green]healthy[/green]")
            healthy_count += 1
        except (httpx.ConnectError, httpx.HTTPStatusError, httpx.TimeoutException):
            table.add_row(name, url, "[red]unreachable[/red]")

    console.print(table)
    console.print(f"\n[bold]{healthy_count}/{total}[/bold] services healthy.")
