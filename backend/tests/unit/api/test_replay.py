"""Tests for POST /api/v1/replay/start and POST /api/v1/replay/stop."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from pitwall.api.dependencies import get_event_loader
from pitwall.api.main import create_app
from pitwall.feeds.base import Event
from pitwall.repositories.events import InMemorySessionEventLoader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_events(n: int = 3, session_id: str = "monaco_2024_R") -> list[Event]:
    t0 = datetime(2024, 5, 26, 13, 0, 0, tzinfo=UTC)
    return [
        {
            "type": "lap_complete",
            "session_id": session_id,
            "ts": t0 + timedelta(seconds=90 * i),
            "payload": {"lap_number": i + 1},
        }
        for i in range(n)
    ]


def _client_with_events(
    sessions: dict[str, list[Event]] | None = None,
) -> TestClient:
    app = create_app()
    loader = InMemorySessionEventLoader(sessions or {})
    app.dependency_overrides[get_event_loader] = lambda: loader
    return TestClient(app)


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------


def test_start_returns_202_with_run_metadata() -> None:
    client = _client_with_events({"monaco_2024_R": _make_events()})
    r = client.post(
        "/api/v1/replay/start",
        json={"session_id": "monaco_2024_R", "speed_factor": 1000},
    )
    assert r.status_code == 202
    body = r.json()
    assert body["session_id"] == "monaco_2024_R"
    assert body["speed_factor"] == pytest.approx(1000.0)
    assert "run_id" in body
    assert "started_at" in body
    assert body["pace_predictor"] in ("scipy", "xgboost")


def test_start_uses_default_speed_factor() -> None:
    client = _client_with_events({"monaco_2024_R": _make_events()})
    r = client.post("/api/v1/replay/start", json={"session_id": "monaco_2024_R"})
    assert r.status_code == 202
    assert r.json()["speed_factor"] == pytest.approx(30.0)


def test_start_404_when_session_unknown() -> None:
    client = _client_with_events()  # empty loader
    r = client.post(
        "/api/v1/replay/start",
        json={"session_id": "bahrain_2024_R", "speed_factor": 1000},
    )
    assert r.status_code == 404
    assert "bahrain_2024_R" in r.json()["detail"]


def test_start_409_when_already_running() -> None:
    """409 is returned when is_running is True.

    We inject a mock manager that permanently reports is_running=True so
    the test is not sensitive to asyncio task scheduling timing.
    """
    from unittest.mock import MagicMock, PropertyMock

    from pitwall.api.dependencies import get_replay_manager

    app = create_app()
    mock_manager = MagicMock()
    type(mock_manager).is_running = PropertyMock(return_value=True)
    mock_manager.current_session_id = "monaco_2024_R"
    # Override the DI provider so the route receives our mock
    app.dependency_overrides[get_replay_manager] = lambda: mock_manager

    loader = InMemorySessionEventLoader({"hungary_2024_R": _make_events(session_id="hungary_2024_R")})
    app.dependency_overrides[get_event_loader] = lambda: loader

    client = TestClient(app)
    r = client.post(
        "/api/v1/replay/start",
        json={"session_id": "hungary_2024_R", "speed_factor": 1000},
    )
    assert r.status_code == 409
    assert "already running" in r.json()["detail"].lower()


def test_start_400_on_bad_speed_factor() -> None:
    client = _client_with_events({"monaco_2024_R": _make_events()})
    r = client.post(
        "/api/v1/replay/start",
        json={"session_id": "monaco_2024_R", "speed_factor": 0},
    )
    assert r.status_code == 422  # Pydantic validation: ge=1.0


# ---------------------------------------------------------------------------
# /stop
# ---------------------------------------------------------------------------


def test_stop_after_start_returns_stopped_true_with_run_id() -> None:
    client = _client_with_events({"monaco_2024_R": _make_events()})
    r_start = client.post(
        "/api/v1/replay/start",
        json={"session_id": "monaco_2024_R", "speed_factor": 1000},
    )
    run_id = r_start.json()["run_id"]

    r_stop = client.post("/api/v1/replay/stop")
    assert r_stop.status_code == 200
    body = r_stop.json()
    assert body["stopped"] is True
    assert body["run_id"] == run_id


def test_stop_when_not_running_returns_stopped_false() -> None:
    client = _client_with_events()
    r = client.post("/api/v1/replay/stop")
    assert r.status_code == 200
    body = r.json()
    assert body["stopped"] is False
    assert body["run_id"] is None


def test_stop_is_idempotent() -> None:
    client = _client_with_events({"monaco_2024_R": _make_events()})
    client.post(
        "/api/v1/replay/start",
        json={"session_id": "monaco_2024_R", "speed_factor": 1000},
    )
    client.post("/api/v1/replay/stop")

    # Second stop must still return 200
    r = client.post("/api/v1/replay/stop")
    assert r.status_code == 200
    assert r.json()["stopped"] is False
