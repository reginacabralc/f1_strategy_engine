"""Tests for GET /api/v1/backtest/{session_id}."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

from pitwall.api.dependencies import get_event_loader
from pitwall.api.main import create_app
from pitwall.feeds.base import Event

_TS = datetime(2024, 5, 26, 13, 0, 0, tzinfo=UTC)


class _Loader:
    async def load_events(self, session_id: str) -> list[Event]:
        return [
            {
                "type": "session_start",
                "session_id": session_id,
                "ts": _TS,
                "payload": {"circuit_id": "monaco", "total_laps": 78, "drivers": ["VER"]},
            },
            {
                "type": "lap_complete",
                "session_id": session_id,
                "ts": _TS,
                "payload": {
                    "driver_code": "VER",
                    "lap_number": 1,
                    "position": 1,
                    "gap_to_leader_ms": 0,
                    "compound": "MEDIUM",
                    "tyre_age": 1,
                    "lap_time_ms": 80_000,
                    "is_valid": True,
                    "is_pit_in": False,
                    "is_pit_out": False,
                    "track_status": "GREEN",
                },
            },
        ]


def test_backtest_route_returns_real_result_when_events_exist() -> None:
    app = create_app()
    app.dependency_overrides[get_event_loader] = lambda: _Loader()

    with TestClient(app) as client:
        response = client.get("/api/v1/backtest/monaco_2024_R?predictor=scipy")

    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    assert body["session_id"] == "monaco_2024_R"
    assert body["predictor"] == "scipy"
    assert body["precision"] == 0.0
    assert body["recall"] == 0.0
    assert body["f1"] == 0.0
