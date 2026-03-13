"""FastAPI dependency injection for the World State Ledger service."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from world_state_ledger.cache import StateCache
from world_state_ledger.event_log import EventLog
from world_state_ledger.state_manager import StateManager


def _get_state_manager(request: Request) -> StateManager:
    """Extract the StateManager from the app state."""
    return request.app.state.state_manager


def _get_event_log(request: Request) -> EventLog:
    """Extract the EventLog from the app state."""
    return request.app.state.event_log


def _get_state_cache(request: Request) -> StateCache:
    """Extract the StateCache from the app state."""
    return request.app.state.state_cache


StateManagerDep = Annotated[StateManager, Depends(_get_state_manager)]
EventLogDep = Annotated[EventLog, Depends(_get_event_log)]
StateCacheDep = Annotated[StateCache, Depends(_get_state_cache)]
