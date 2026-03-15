"""Temporal activity definitions for the World State Ledger.

Activities are methods on the ``WSLActivities`` dataclass, which holds typed
references to the real service-layer objects.  An instance is created at
worker startup and registered with the Temporal worker.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from temporalio import activity

from architect_common.logging import get_logger
from world_state_ledger.event_log import EventLog
from world_state_ledger.models import Proposal
from world_state_ledger.state_manager import StateManager

logger = get_logger(component="world_state_ledger.temporal.activities")


@dataclass
class WSLActivities:
    """Holds live service-layer dependencies for Temporal activities."""

    state_manager: StateManager
    event_log: EventLog

    @activity.defn
    async def get_current_state(self) -> dict[str, Any]:
        """Return the current world state as a plain dict."""
        state = await self.state_manager.get_current()
        return state.model_dump(mode="json")

    @activity.defn
    async def submit_proposal(self, proposal_data: dict[str, Any]) -> str:
        """Persist a new proposal and return its ID."""
        proposal = Proposal.model_validate(proposal_data)
        return await self.state_manager.submit_proposal(proposal)

    @activity.defn
    async def validate_and_commit(self, proposal_id: str) -> bool:
        """Validate and commit a pending proposal."""
        return await self.state_manager.validate_and_commit(proposal_id)
