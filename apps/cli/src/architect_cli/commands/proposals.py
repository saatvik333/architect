"""ARCHITECT CLI — proposals command implementation."""

from __future__ import annotations

import json

import httpx
import typer
from rich.syntax import Syntax
from rich.table import Table

from architect_cli.output import console, print_error


def proposals_list(
    task_id: str,
    gateway_url: str = "http://localhost:8000",
) -> None:
    """List proposals for a task."""
    try:
        with httpx.Client(base_url=gateway_url, timeout=30.0) as client:
            resp = client.get(f"/api/v1/tasks/{task_id}/proposals")
            resp.raise_for_status()
            proposals = resp.json()

        if not proposals:
            console.print("[dim]No proposals found for this task.[/dim]")
            return

        table = Table(title=f"Proposals for {task_id}", show_header=True)
        table.add_column("Proposal ID", style="bold")
        table.add_column("Agent")
        table.add_column("Verdict")
        table.add_column("Created")

        for p in proposals:
            verdict = p.get("verdict", "pending")
            verdict_styled = {
                "approved": "[green]approved[/green]",
                "rejected": "[red]rejected[/red]",
                "pending": "[yellow]pending[/yellow]",
            }.get(verdict.lower(), verdict)

            table.add_row(
                p.get("proposal_id", "?"),
                p.get("agent_id", "?"),
                verdict_styled,
                p.get("created_at", "?"),
            )

        console.print(table)

    except httpx.HTTPStatusError as exc:
        print_error(f"HTTP {exc.response.status_code}: {exc.response.text}")
        raise typer.Exit(code=1) from None
    except httpx.ConnectError:
        print_error(f"Cannot connect to gateway at {gateway_url}")
        raise typer.Exit(code=1) from None


def proposals_inspect(
    proposal_id: str,
    gateway_url: str = "http://localhost:8000",
) -> None:
    """Show detailed proposal with mutations."""
    try:
        with httpx.Client(base_url=gateway_url, timeout=30.0) as client:
            resp = client.get(f"/api/v1/proposals/{proposal_id}")
            resp.raise_for_status()
            data = resp.json()

        console.print(f"\n[bold]Proposal:[/bold] {data.get('proposal_id', proposal_id)}")
        console.print(f"[bold]Task:[/bold]     {data.get('task_id', 'N/A')}")
        console.print(f"[bold]Agent:[/bold]    {data.get('agent_id', 'N/A')}")
        console.print(f"[bold]Verdict:[/bold]  {data.get('verdict', 'N/A')}")
        console.print(f"[bold]Created:[/bold]  {data.get('created_at', 'N/A')}")

        mutations = data.get("mutations", [])
        if mutations:
            console.print(f"\n[bold]Mutations ({len(mutations)}):[/bold]")
            formatted = json.dumps(mutations, indent=2)
            console.print(Syntax(formatted, "json", theme="monokai"))

    except httpx.HTTPStatusError as exc:
        print_error(f"HTTP {exc.response.status_code}: {exc.response.text}")
        raise typer.Exit(code=1) from None
    except httpx.ConnectError:
        print_error(f"Cannot connect to gateway at {gateway_url}")
        raise typer.Exit(code=1) from None
