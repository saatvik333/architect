"""Event subscription handlers for the Human Interface service.

Listens for system events and escalation messages, broadcasting relevant
updates to connected WebSocket dashboard clients.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from architect_common.logging import get_logger
from architect_common.types import utcnow

if TYPE_CHECKING:
    from architect_events.schemas import EventEnvelope
    from human_interface.ws_manager import WebSocketManager

logger = get_logger(component="human_interface.event_handlers")


async def _broadcast_event(
    envelope: EventEnvelope,
    ws_manager: WebSocketManager,
    *,
    message_type: str,
) -> None:
    """Transform an event envelope into a WebSocket message and broadcast it.

    Args:
        envelope: The incoming event from the event bus.
        ws_manager: The WebSocket connection manager.
        message_type: The ``type`` field for the outgoing WebSocket message
            (e.g. ``"system_event"`` or ``"escalation_event"``).
    """
    message = {
        "type": message_type,
        "data": {
            "event_id": envelope.id,
            "event_type": envelope.type,
            "correlation_id": envelope.correlation_id,
            "payload": envelope.payload,
        },
        "timestamp": utcnow().isoformat(),
    }
    await ws_manager.broadcast(message)


async def handle_system_event(
    envelope: EventEnvelope,
    ws_manager: WebSocketManager,
) -> None:
    """Broadcast a system event to all connected WebSocket clients."""
    logger.debug("handling system event", event_type=envelope.type, event_id=envelope.id)
    await _broadcast_event(envelope, ws_manager, message_type="system_event")


async def handle_escalation_message(
    envelope: EventEnvelope,
    ws_manager: WebSocketManager,
) -> None:
    """Broadcast an escalation event to all connected WebSocket clients."""
    logger.info("handling escalation event", event_type=envelope.type, event_id=envelope.id)
    await _broadcast_event(envelope, ws_manager, message_type="escalation_event")
