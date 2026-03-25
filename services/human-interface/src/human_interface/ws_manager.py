"""WebSocket connection manager for real-time dashboard updates."""

from __future__ import annotations

import json
from typing import Any

from fastapi import WebSocket

from architect_common.logging import get_logger

logger = get_logger(component="human_interface.ws_manager")


class WebSocketManager:
    """Manages active WebSocket connections and broadcasts messages."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    @property
    def connection_count(self) -> int:
        """Return the number of active connections."""
        return len(self._connections)

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection.

        Args:
            websocket: The incoming WebSocket to accept.
        """
        await websocket.accept()
        self._connections.add(websocket)
        logger.info("websocket connected", total_connections=len(self._connections))

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection from the active set.

        Args:
            websocket: The WebSocket that disconnected.
        """
        self._connections.discard(websocket)
        logger.info("websocket disconnected", total_connections=len(self._connections))

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send a JSON message to all connected clients.

        Disconnected or errored clients are removed in a single batch
        after the broadcast completes.

        Args:
            message: The message payload to broadcast.
        """
        payload = json.dumps(message, default=str)
        stale: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(payload)
            except Exception:
                logger.debug("removing stale websocket connection")
                stale.append(ws)

        if stale:
            self._connections -= set(stale)
