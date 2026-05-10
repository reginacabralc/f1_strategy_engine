"""WebSocket connection manager.

Holds the set of active ``/ws/v1/live`` WebSocket connections and
fans out JSON messages to all of them.  Dead connections are removed
silently on the next broadcast attempt.

``ConnectionManager`` satisfies the :class:`~pitwall.engine.loop.Broadcaster`
Protocol so the :class:`~pitwall.engine.loop.EngineLoop` can broadcast
without importing from the ``api`` package.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from starlette.websockets import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Fan-out broadcaster for active WebSocket connections.

    Thread safety: designed for a single asyncio event loop.
    """

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self, ws: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await ws.accept()
        self._connections.add(ws)
        logger.debug("WS connected; active=%d", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        """Deregister a WebSocket (called when the client disconnects)."""
        self._connections.discard(ws)
        logger.debug("WS disconnected; active=%d", len(self._connections))

    # ------------------------------------------------------------------
    # Broadcasting
    # ------------------------------------------------------------------

    async def broadcast_json(self, data: dict[str, Any]) -> None:
        """Send *data* to every connected client.

        Connections that fail to receive within 1 s (dead clients, slow
        networks) are removed — master plan § WebSocket backpressure.
        """
        dead: set[WebSocket] = set()
        for ws in list(self._connections):
            try:
                await asyncio.wait_for(ws.send_json(data), timeout=1.0)
            except (TimeoutError, WebSocketDisconnect, RuntimeError, Exception):
                dead.add(ws)
        for ws in dead:
            self._connections.discard(ws)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def count(self) -> int:
        """Number of active connections."""
        return len(self._connections)
