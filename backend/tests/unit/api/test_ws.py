"""Tests for the WebSocket endpoint and ConnectionManager."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from pitwall.api.connections import ConnectionManager
from pitwall.api.main import create_app


# ---------------------------------------------------------------------------
# ConnectionManager unit tests (mock WebSocket)
# ---------------------------------------------------------------------------


class _MockWebSocket:
    """Minimal WebSocket double for ConnectionManager testing."""

    def __init__(self, *, fail_on_send: bool = False) -> None:
        self.accepted = False
        self.sent: list[dict[str, Any]] = []
        self.fail_on_send = fail_on_send

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, data: dict[str, Any]) -> None:
        if self.fail_on_send:
            raise RuntimeError("connection closed")
        self.sent.append(data)


async def test_connection_manager_tracks_connected_clients() -> None:
    cm = ConnectionManager()
    ws1 = _MockWebSocket()
    ws2 = _MockWebSocket()

    await cm.connect(ws1)
    await cm.connect(ws2)

    assert cm.count == 2
    assert ws1.accepted
    assert ws2.accepted


async def test_connection_manager_disconnect_reduces_count() -> None:
    cm = ConnectionManager()
    ws = _MockWebSocket()
    await cm.connect(ws)
    cm.disconnect(ws)
    assert cm.count == 0


async def test_connection_manager_broadcast_sends_to_all() -> None:
    cm = ConnectionManager()
    ws1 = _MockWebSocket()
    ws2 = _MockWebSocket()
    await cm.connect(ws1)
    await cm.connect(ws2)

    payload = {"v": 1, "type": "ping", "ts": "now", "payload": {}}
    await cm.broadcast_json(payload)

    assert ws1.sent == [payload]
    assert ws2.sent == [payload]


async def test_connection_manager_removes_dead_connection_on_send_failure() -> None:
    cm = ConnectionManager()
    live = _MockWebSocket()
    dead = _MockWebSocket(fail_on_send=True)
    await cm.connect(live)
    await cm.connect(dead)

    await cm.broadcast_json({"type": "test"})

    assert cm.count == 1
    assert len(live.sent) == 1


async def test_connection_manager_broadcast_to_empty_set_is_noop() -> None:
    cm = ConnectionManager()
    await cm.broadcast_json({"type": "test"})  # must not raise
    assert cm.count == 0


# ---------------------------------------------------------------------------
# WebSocket endpoint (TestClient)
# ---------------------------------------------------------------------------


def test_ws_live_endpoint_accepts_connection() -> None:
    """The /ws/v1/live endpoint must accept and survive a clean disconnect."""
    app = create_app()
    with TestClient(app) as client:
        with client.websocket_connect("/ws/v1/live") as ws:
            # Connection accepted — we don't send anything, just disconnect
            pass  # __exit__ sends close frame


def test_ws_live_endpoint_is_in_openapi_paths() -> None:
    """The WS path must NOT appear in the OpenAPI HTTP spec."""
    app = create_app()
    spec = app.openapi()
    # WebSocket routes are not listed in OpenAPI 3.0 HTTP paths
    assert "/ws/v1/live" not in spec.get("paths", {})
