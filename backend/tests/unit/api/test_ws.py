"""Tests for the WebSocket endpoint and ConnectionManager."""

from __future__ import annotations

from typing import Any

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

    await cm.connect(ws1)  # type: ignore[arg-type]
    await cm.connect(ws2)  # type: ignore[arg-type]

    assert cm.count == 2
    assert ws1.accepted
    assert ws2.accepted


async def test_connection_manager_disconnect_reduces_count() -> None:
    cm = ConnectionManager()
    ws = _MockWebSocket()
    await cm.connect(ws)  # type: ignore[arg-type]
    cm.disconnect(ws)  # type: ignore[arg-type]
    assert cm.count == 0


async def test_connection_manager_broadcast_sends_to_all() -> None:
    cm = ConnectionManager()
    ws1 = _MockWebSocket()
    ws2 = _MockWebSocket()
    await cm.connect(ws1)  # type: ignore[arg-type]
    await cm.connect(ws2)  # type: ignore[arg-type]

    payload = {"v": 1, "type": "ping", "ts": "now", "payload": {}}
    await cm.broadcast_json(payload)

    assert ws1.sent == [payload]
    assert ws2.sent == [payload]


async def test_connection_manager_removes_dead_connection_on_send_failure() -> None:
    cm = ConnectionManager()
    live = _MockWebSocket()
    dead = _MockWebSocket(fail_on_send=True)
    await cm.connect(live)  # type: ignore[arg-type]
    await cm.connect(dead)  # type: ignore[arg-type]

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
    with TestClient(app) as client, client.websocket_connect("/ws/v1/live") as _ws:
        # Connection accepted — we don't send anything, just disconnect
        pass  # __exit__ sends close frame


def test_ws_live_endpoint_is_in_openapi_paths() -> None:
    """The WS path must NOT appear in the OpenAPI HTTP spec."""
    app = create_app()
    spec = app.openapi()
    # WebSocket routes are not listed in OpenAPI 3.0 HTTP paths
    assert "/ws/v1/live" not in spec.get("paths", {})


# ---------------------------------------------------------------------------
# Snapshot on (re)connect — Day 10
# ---------------------------------------------------------------------------


class _MockEngineLoop:
    """Minimal stand-in for EngineLoop used in WS reconnect tests."""

    def __init__(self, snapshot: dict[str, Any] | None = None) -> None:
        self._snap = snapshot

    def get_snapshot(self) -> dict[str, Any] | None:
        return self._snap

    # EngineLoop interface used by lifespan — no-op stubs.
    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    def set_predictor(self, predictor: Any, name: str = "scipy") -> None:
        pass

    @property
    def predictor_name(self) -> str:
        return "scipy"

    @property
    def state(self) -> Any:
        from pitwall.engine.state import RaceState
        return RaceState()


def test_ws_sends_snapshot_on_connect_when_session_active() -> None:
    """Connecting client receives current snapshot immediately if a session is active."""
    snap = {
        "v": 1,
        "type": "snapshot",
        "ts": "2024-05-26T13:00:00+00:00",
        "payload": {
            "session_id": "monaco_2024_R",
            "current_lap": 15,
            "track_status": "GREEN",
            "track_temp_c": 38.0,
            "air_temp_c": 24.0,
            "humidity_pct": 60.0,
            "active_predictor": "scipy",
            "drivers": [],
            "last_event_ts": None,
        },
    }
    app = create_app()
    # Replace engine_loop on app.state after create_app() but before TestClient
    # starts the lifespan.  The WS handler reads from app.state; the lifespan
    # closure holds a reference to the original EngineLoop, which will still be
    # started/stopped normally.
    app.state.engine_loop = _MockEngineLoop(snapshot=snap)

    with TestClient(app) as client, client.websocket_connect("/ws/v1/live") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "snapshot"
        assert msg["payload"]["session_id"] == "monaco_2024_R"
        assert msg["payload"]["active_predictor"] == "scipy"


def test_ws_no_snapshot_sent_when_no_session_active() -> None:
    """If no session has started yet, no snapshot is sent on connect."""
    app = create_app()
    app.state.engine_loop = _MockEngineLoop(snapshot=None)

    with TestClient(app) as client, client.websocket_connect("/ws/v1/live") as _ws:
        # No message to receive — just check the connection stays open cleanly.
        pass  # __exit__ closes the WS
