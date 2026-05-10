"""WebSocket route — /ws/v1/live.

Clients connect here to receive a real-time stream of:
- ``snapshot``  — full race state after every ``lap_complete`` event.
- ``alert``     — undercut-viability notifications from the engine.
- ``ping``      — heartbeat sent every 15 s by the server.

Message format (envelope):
    {
        "v": 1,
        "type": "<snapshot|alert|ping>",
        "ts": "<ISO-8601 UTC>",
        "payload": { ... }
    }

The endpoint keeps the connection alive by reading incoming frames.
Client messages are accepted but ignored in V1 (other than implicitly
keeping the TCP connection open).  ``pong`` frames from the client reset
the 15 s heartbeat timer.

See ``docs/interfaces/websocket_messages.md`` for the full message spec.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter
from starlette.websockets import WebSocket, WebSocketDisconnect

from pitwall.api.connections import ConnectionManager

router = APIRouter()

_HEARTBEAT_INTERVAL = 15.0  # seconds


@router.websocket("/ws/v1/live")
async def ws_live(websocket: WebSocket) -> None:
    """Accept a live WebSocket connection and hold it open."""
    # Access ConnectionManager via app.state — DI Request injection does not
    # work in WebSocket handlers the same way as in HTTP route handlers.
    cm: ConnectionManager = websocket.app.state.connection_manager
    await cm.connect(websocket)
    try:
        while True:
            try:
                # Block until the client sends any frame OR the heartbeat interval
                # expires, whichever comes first.
                await asyncio.wait_for(
                    websocket.receive_bytes(),
                    timeout=_HEARTBEAT_INTERVAL,
                )
                # Client frame received — ignore content (V1).
            except asyncio.TimeoutError:
                # No message from client in 15 s — send a ping so slow clients
                # are detected by their next failed receive.
                try:
                    await websocket.send_json({
                        "v": 1,
                        "type": "ping",
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "payload": {},
                    })
                except Exception:
                    break  # connection is gone
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        cm.disconnect(websocket)
