"""Tests for the WebSocket connection manager."""

from __future__ import annotations

from unittest.mock import AsyncMock

from human_interface.ws_manager import WebSocketManager


class TestWebSocketManager:
    """Verify WebSocket manager connect/disconnect/broadcast behavior."""

    async def test_connect_adds_websocket(self, ws_manager: WebSocketManager) -> None:
        ws = AsyncMock()
        await ws_manager.connect(ws)
        assert ws_manager.connection_count == 1
        ws.accept.assert_awaited_once()

    async def test_disconnect_removes_websocket(self, ws_manager: WebSocketManager) -> None:
        ws = AsyncMock()
        await ws_manager.connect(ws)
        assert ws_manager.connection_count == 1
        await ws_manager.disconnect(ws)
        assert ws_manager.connection_count == 0

    async def test_disconnect_unknown_websocket(self, ws_manager: WebSocketManager) -> None:
        """Disconnecting a non-tracked WebSocket should not raise."""
        ws = AsyncMock()
        await ws_manager.disconnect(ws)
        assert ws_manager.connection_count == 0

    async def test_broadcast_sends_to_all(self, ws_manager: WebSocketManager) -> None:
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await ws_manager.connect(ws1)
        await ws_manager.connect(ws2)

        await ws_manager.broadcast({"type": "test", "data": "hello"})

        ws1.send_text.assert_awaited_once()
        ws2.send_text.assert_awaited_once()

    async def test_broadcast_removes_stale_connections(self, ws_manager: WebSocketManager) -> None:
        ws_good = AsyncMock()
        ws_bad = AsyncMock()
        ws_bad.send_text.side_effect = Exception("connection closed")

        await ws_manager.connect(ws_good)
        await ws_manager.connect(ws_bad)
        assert ws_manager.connection_count == 2

        await ws_manager.broadcast({"type": "test"})

        # Stale connection should have been removed.
        assert ws_manager.connection_count == 1
        ws_good.send_text.assert_awaited_once()

    async def test_broadcast_empty_message(self, ws_manager: WebSocketManager) -> None:
        ws = AsyncMock()
        await ws_manager.connect(ws)
        await ws_manager.broadcast({})
        ws.send_text.assert_awaited_once()

    async def test_broadcast_no_connections(self, ws_manager: WebSocketManager) -> None:
        """Broadcasting with no connections should not raise."""
        await ws_manager.broadcast({"type": "test"})
        assert ws_manager.connection_count == 0

    async def test_multiple_connect_disconnect(self, ws_manager: WebSocketManager) -> None:
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws3 = AsyncMock()

        await ws_manager.connect(ws1)
        await ws_manager.connect(ws2)
        await ws_manager.connect(ws3)
        assert ws_manager.connection_count == 3

        await ws_manager.disconnect(ws2)
        assert ws_manager.connection_count == 2

        await ws_manager.broadcast({"type": "test"})
        ws1.send_text.assert_awaited_once()
        ws3.send_text.assert_awaited_once()
        ws2.send_text.assert_not_awaited()

    async def test_max_connections_enforcement(self) -> None:
        """When max_connections is reached, new connections should be rejected."""
        manager = WebSocketManager(max_connections=2)

        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws3 = AsyncMock()

        await manager.connect(ws1)
        await manager.connect(ws2)
        assert manager.connection_count == 2

        # Third connection should be rejected
        await manager.connect(ws3)
        assert manager.connection_count == 2
        ws3.close.assert_awaited_once()
        ws3.accept.assert_not_awaited()

    async def test_connection_count_tracking(self) -> None:
        """Connection count should accurately track connect/disconnect cycles."""
        manager = WebSocketManager(max_connections=10)

        connections = [AsyncMock() for _ in range(5)]

        # Connect all
        for ws in connections:
            await manager.connect(ws)
        assert manager.connection_count == 5

        # Disconnect two
        await manager.disconnect(connections[1])
        await manager.disconnect(connections[3])
        assert manager.connection_count == 3

        # Connect one more
        ws_new = AsyncMock()
        await manager.connect(ws_new)
        assert manager.connection_count == 4

        # Disconnect all remaining
        for ws in [connections[0], connections[2], connections[4], ws_new]:
            await manager.disconnect(ws)
        assert manager.connection_count == 0

    async def test_max_connections_allows_reconnect_after_disconnect(self) -> None:
        """After a disconnect, a new connection should be accepted even at max."""
        manager = WebSocketManager(max_connections=1)

        ws1 = AsyncMock()
        await manager.connect(ws1)
        assert manager.connection_count == 1

        # Reject second
        ws2 = AsyncMock()
        await manager.connect(ws2)
        assert manager.connection_count == 1

        # Disconnect first, then second should succeed
        await manager.disconnect(ws1)
        assert manager.connection_count == 0

        ws3 = AsyncMock()
        await manager.connect(ws3)
        assert manager.connection_count == 1
        ws3.accept.assert_awaited_once()
