"""Tests for GET /api/v1/sessions/{session_id}/snapshot."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from pitwall.api.dependencies import get_engine_loop, get_replay_manager
from pitwall.api.main import create_app
from pitwall.engine.state import DriverState, RaceState


def _make_app(
    *,
    replay_running: bool = False,
    session_id: str = "monaco_2024_R",
    state: RaceState | None = None,
    predictor_name: str = "scipy",
) -> TestClient:
    app = create_app()

    mock_replay = MagicMock()
    mock_replay.is_running = replay_running
    mock_replay.current_session_id = session_id if replay_running else None

    mock_loop = MagicMock()
    mock_loop.state = state or RaceState()
    mock_loop.predictor_name = predictor_name

    app.dependency_overrides[get_replay_manager] = lambda: mock_replay
    app.dependency_overrides[get_engine_loop] = lambda: mock_loop
    return TestClient(app)


# ---------------------------------------------------------------------------
# 404 cases
# ---------------------------------------------------------------------------


def test_snapshot_404_when_no_replay_running() -> None:
    client = _make_app(replay_running=False)
    r = client.get("/api/v1/sessions/monaco_2024_R/snapshot")
    assert r.status_code == 404


def test_snapshot_404_when_replay_running_for_different_session() -> None:
    client = _make_app(replay_running=True, session_id="hungary_2024_R")
    r = client.get("/api/v1/sessions/monaco_2024_R/snapshot")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# 200 cases — shape and values
# ---------------------------------------------------------------------------


def test_snapshot_200_when_replay_active_for_requested_session() -> None:
    client = _make_app(replay_running=True, session_id="monaco_2024_R")
    r = client.get("/api/v1/sessions/monaco_2024_R/snapshot")
    assert r.status_code == 200


def test_snapshot_response_contains_required_fields() -> None:
    client = _make_app(replay_running=True, session_id="monaco_2024_R")
    body = client.get("/api/v1/sessions/monaco_2024_R/snapshot").json()

    assert "session_id" in body
    assert "current_lap" in body
    assert "track_status" in body
    assert "drivers" in body
    assert "active_predictor" in body
    assert "last_event_ts" in body


def test_snapshot_active_predictor_reflects_engine_loop() -> None:
    client = _make_app(replay_running=True, session_id="monaco_2024_R", predictor_name="xgboost")
    body = client.get("/api/v1/sessions/monaco_2024_R/snapshot").json()
    assert body["active_predictor"] == "xgboost"


def test_snapshot_includes_driver_states() -> None:
    state = RaceState()
    state.session_id = "monaco_2024_R"
    state.current_lap = 15
    state.track_status = "GREEN"
    state.drivers["VER"] = DriverState(
        driver_code="VER",
        position=1,
        compound="HARD",
        tyre_age=12,
        gap_to_leader_ms=0,
        undercut_score=None,
    )
    state.drivers["LEC"] = DriverState(
        driver_code="LEC",
        position=2,
        compound="MEDIUM",
        tyre_age=8,
        gap_to_leader_ms=5_200,
        gap_to_ahead_ms=5_200,
        undercut_score=0.65,
    )

    client = _make_app(
        replay_running=True,
        session_id="monaco_2024_R",
        state=state,
    )
    body = client.get("/api/v1/sessions/monaco_2024_R/snapshot").json()

    assert body["current_lap"] == 15
    assert body["track_status"] == "GREEN"
    assert len(body["drivers"]) == 2

    by_code = {d["driver_code"]: d for d in body["drivers"]}
    assert by_code["VER"]["position"] == 1
    assert by_code["VER"]["compound"] == "HARD"
    assert by_code["LEC"]["undercut_score"] == pytest.approx(0.65)


def test_snapshot_drivers_sorted_by_position() -> None:
    state = RaceState()
    state.session_id = "monaco_2024_R"
    for code, pos in [("NOR", 3), ("VER", 1), ("LEC", 2)]:
        state.drivers[code] = DriverState(driver_code=code, position=pos)

    client = _make_app(replay_running=True, session_id="monaco_2024_R", state=state)
    body = client.get("/api/v1/sessions/monaco_2024_R/snapshot").json()

    positions = [d["position"] for d in body["drivers"]]
    assert positions == [1, 2, 3]
