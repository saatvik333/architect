"""Temporal activity definitions for the World State Ledger.

Activities are thin wrappers that delegate to the real service-layer objects.
The actual ``StateManager`` and ``EventLog`` instances are injected at worker
startup time via a module-level registry so that ``@activity.defn`` functions
can access them without Temporal needing to know about our DI setup.
"""

from __future__ import annotations

from typing import Any, cast

from temporalio import activity

from architect_common.logging import get_logger

logger = get_logger(component="world_state_ledger.temporal.activities")

# ── Runtime registry (populated by the worker on startup) ────────────

_state_manager: Any = None
_event_log: Any = None


def register_dependencies(state_manager: Any, event_log: Any) -> None:
    """Inject the live StateManager and EventLog into the activity module."""
    global _state_manager, _event_log
    _state_manager = state_manager
    _event_log = event_log


# ── Activities ───────────────────────────────────────────────────────


@activity.defn
async def get_current_state() -> dict[str, Any]:
    """Return the current world state as a plain dict."""
    if _state_manager is None:
        msg = "StateManager not registered — call register_dependencies first"
        raise RuntimeError(msg)
    state = await _state_manager.get_current()
    return cast(dict[str, Any], state.model_dump(mode="json"))


@activity.defn
async def submit_proposal(proposal_data: dict[str, Any]) -> str:
    """Persist a new proposal and return its ID."""
    if _state_manager is None:
        msg = "StateManager not registered — call register_dependencies first"
        raise RuntimeError(msg)

    from world_state_ledger.models import Proposal

    proposal = Proposal.model_validate(proposal_data)
    return cast(str, await _state_manager.submit_proposal(proposal))


@activity.defn
async def validate_and_commit(proposal_id: str) -> bool:
    """Validate and commit a pending proposal."""
    if _state_manager is None:
        msg = "StateManager not registered — call register_dependencies first"
        raise RuntimeError(msg)
    return cast(bool, await _state_manager.validate_and_commit(proposal_id))
