"""WebSocket connection manager for real-time dashboard updates."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import WebSocket

from architect_common.logging import get_logger

logger = get_logger(component="human_interface.ws_manager")


class WebSocketManager:
    """Manages active WebSocket connections and broadcasts messages."""

    def __init__(self, *, max_connections: int = 100) -> None:
        self._connections: set[WebSocket] = set()
        self._max_connections = max_connections
        self._lock = asyncio.Lock()

    @property
    def connection_count(self) -> int:
        """Return the number of active connections."""
        return len(self._connections)

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection.

        Args:
            websocket: The incoming WebSocket to accept.
        """
        async with self._lock:
            if len(self._connections) >= self._max_connections:
                logger.warning(
                    "connection limit reached, rejecting websocket",
                    max_connections=self._max_connections,
                )
                await websocket.close(code=4002, reason="Too many connections")
                return
            await websocket.accept()
            self._connections.add(websocket)
            logger.info("websocket connected", total_connections=len(self._connections))

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection from the active set.

        Args:
            websocket: The WebSocket that disconnected.
        """
        async with self._lock:
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

        async with self._lock:
            snapshot = set(self._connections)

        async def _send(ws: WebSocket) -> WebSocket | None:
            try:
                await ws.send_text(payload)
            except Exception:
                logger.debug("removing stale websocket connection")
                return ws
            return None

        results = await asyncio.gather(*[_send(ws) for ws in snapshot])
        stale = [ws for ws in results if ws is not None]

        if stale:
            async with self._lock:
                self._connections -= set(stale)
