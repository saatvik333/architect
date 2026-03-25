"""Temporal workflow definitions for the Human Interface."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from human_interface.temporal.activities import (
        expire_escalation_activity,
        resolve_escalation_activity,
    )


TASK_QUEUE = "human-interface"


@workflow.defn
class EscalationTimeoutWorkflow:
    """Sleeps until an escalation's expiry time, then auto-resolves it.

    Starts when an escalation is created with a finite expiry.  If the
    escalation is resolved before the timeout fires, the workflow should
    be cancelled externally.
    """

    @workflow.run
    async def run(self, params: dict[str, Any]) -> dict[str, Any]:
        """Wait until expiry, then expire the escalation.

        Args:
            params: Dict with ``escalation_id`` and ``timeout_seconds``.

        Returns:
            Dict indicating whether the escalation was expired.
        """
        escalation_id = params["escalation_id"]
        timeout_seconds = params.get("timeout_seconds", 3600)

        workflow.logger.info(
            f"Waiting {timeout_seconds}s before expiring escalation {escalation_id}"
        )

        await workflow.sleep(timedelta(seconds=timeout_seconds))

        result: dict[str, Any] = await workflow.execute_activity(
            expire_escalation_activity,
            args=[{"escalation_id": escalation_id}],
            start_to_close_timeout=timedelta(seconds=30),
        )

        return {
            "escalation_id": escalation_id,
            "expired": True,
            "result": result,
        }


@workflow.defn
class ApprovalGateWorkflow:
    """Waits for approval vote signals and resolves the gate when quorum is met.

    Uses Temporal signals to receive vote notifications without polling.
    """

    def __init__(self) -> None:
        self._votes: list[dict[str, Any]] = []
        self._resolved = False
        self._final_status = "pending"

    @workflow.signal
    async def vote(self, vote_data: dict[str, Any]) -> None:
        """Receive a vote signal.

        Args:
            vote_data: Dict with ``voter``, ``decision``, ``comment``.
        """
        self._votes.append(vote_data)

        decision = vote_data.get("decision", "")
        if decision == "deny":
            self._resolved = True
            self._final_status = "denied"
            return

        # Check if we've hit the required approval count.
        approval_count = sum(1 for v in self._votes if v.get("decision") == "approve")
        required = vote_data.get("required_approvals", 1)
        if approval_count >= required:
            self._resolved = True
            self._final_status = "approved"

    @workflow.run
    async def run(self, params: dict[str, Any]) -> dict[str, Any]:
        """Wait for votes until the gate is resolved or times out.

        Args:
            params: Dict with ``gate_id``, ``required_approvals``,
                    and ``timeout_seconds``.

        Returns:
            Dict with gate resolution status and votes received.
        """
        gate_id = params["gate_id"]
        timeout_seconds = params.get("timeout_seconds", 3600)

        workflow.logger.info(f"Waiting for votes on gate {gate_id}")

        try:
            await workflow.wait_condition(
                lambda: self._resolved,
                timeout=timedelta(seconds=timeout_seconds),
            )
        except TimeoutError:
            self._final_status = "expired"

        if not self._resolved and self._final_status == "expired":
            # Auto-resolve as expired via activity.
            await workflow.execute_activity(
                resolve_escalation_activity,
                args=[
                    {
                        "escalation_id": gate_id,
                        "resolved_by": "system_timeout",
                        "resolution": "expired",
                    }
                ],
                start_to_close_timeout=timedelta(seconds=30),
            )

        return {
            "gate_id": gate_id,
            "status": self._final_status,
            "votes": self._votes,
        }
