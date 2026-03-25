"""Temporal activity definitions for the Human Interface."""

from __future__ import annotations

from typing import Any

from temporalio import activity


@activity.defn
async def create_escalation_activity(data: dict[str, Any]) -> dict[str, Any]:
    """Create an escalation via the Human Interface API.

    Args:
        data: Dict with escalation fields (summary, category, severity, etc.).

    Returns:
        Dict with the created escalation ID and status.
    """
    activity.logger.info("create_escalation_activity started")

    import httpx

    base_url = data.get("service_url", "http://localhost:8016")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{base_url}/api/v1/escalations", json=data)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]


@activity.defn
async def resolve_escalation_activity(data: dict[str, Any]) -> dict[str, Any]:
    """Resolve an escalation via the Human Interface API.

    Args:
        data: Dict with ``escalation_id``, ``resolved_by``, ``resolution``.

    Returns:
        Dict with the resolved escalation data.
    """
    activity.logger.info("resolve_escalation_activity started")

    import httpx

    base_url = data.get("service_url", "http://localhost:8016")
    escalation_id = data["escalation_id"]
    body = {
        "resolved_by": data.get("resolved_by", "system"),
        "resolution": data.get("resolution", "auto_resolved"),
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{base_url}/api/v1/escalations/{escalation_id}/resolve", json=body
        )
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]


@activity.defn
async def expire_escalation_activity(data: dict[str, Any]) -> dict[str, Any]:
    """Expire a pending escalation that has passed its deadline.

    Args:
        data: Dict with ``escalation_id``.

    Returns:
        Dict with the expired escalation data.
    """
    activity.logger.info("expire_escalation_activity started")

    import httpx

    base_url = data.get("service_url", "http://localhost:8016")
    escalation_id = data["escalation_id"]
    body = {
        "resolved_by": "system_timeout",
        "resolution": "expired",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{base_url}/api/v1/escalations/{escalation_id}/resolve", json=body
        )
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]


@activity.defn
async def create_approval_gate_activity(data: dict[str, Any]) -> dict[str, Any]:
    """Create an approval gate via the Human Interface API.

    Args:
        data: Dict with gate fields (action_type, resource_id, etc.).

    Returns:
        Dict with the created approval gate data.
    """
    activity.logger.info("create_approval_gate_activity started")

    import httpx

    base_url = data.get("service_url", "http://localhost:8016")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{base_url}/api/v1/approval-gates", json=data)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]


@activity.defn
async def fetch_progress_summary_activity(data: dict[str, Any]) -> dict[str, Any]:
    """Fetch a progress summary from the Human Interface API.

    Args:
        data: Dict with optional ``service_url``.

    Returns:
        Dict with the progress summary data.
    """
    activity.logger.info("fetch_progress_summary_activity started")

    import httpx

    base_url = data.get("service_url", "http://localhost:8016")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{base_url}/api/v1/progress")
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]
