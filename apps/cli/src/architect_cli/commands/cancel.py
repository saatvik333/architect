"""ARCHITECT CLI — cancel command implementation."""

from __future__ import annotations

import httpx
import typer

from architect_cli.output import print_error, print_success


def cancel(
    task_id: str,
    gateway_url: str = "http://localhost:8000",
    force: bool = False,
) -> None:
    """Request cancellation of a running task."""
    try:
        with httpx.Client(base_url=gateway_url, timeout=30.0) as client:
            resp = client.post(
                f"/api/v1/tasks/{task_id}/cancel",
                json={"force": force},
            )
            resp.raise_for_status()
            data = resp.json()

        status = data.get("status", "cancelled")
        print_success(f"Task {task_id} cancellation requested (status: {status}).")
        if force:
            cancelled_children = data.get("cancelled_children", [])
            if cancelled_children:
                print_success(f"Also cancelled {len(cancelled_children)} child task(s).")

    except httpx.HTTPStatusError as exc:
        print_error(f"HTTP {exc.response.status_code}: {exc.response.text}")
        raise typer.Exit(code=1) from None
    except httpx.ConnectError:
        print_error(f"Cannot connect to gateway at {gateway_url}")
        raise typer.Exit(code=1) from None
