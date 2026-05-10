"""Tests for ``GET /api/v1/sessions``.

Exercises the route with both the default in-memory repository and a
test repository injected via ``app.dependency_overrides``. The latter
is the pattern Stream A will use on Day 3 when wiring the SQL
implementation behind the same Protocol.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from pitwall.api.dependencies import get_session_repository
from pitwall.api.main import create_app
from pitwall.repositories.sessions import (
    InMemorySessionRepository,
    SessionRow,
)


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_session_repository] = lambda: InMemorySessionRepository()
    return TestClient(app)


# --------------------------------------------------------------------------
# Default fixture (the three demo races verified in Stream A Day 1)
# --------------------------------------------------------------------------


def test_returns_three_demo_races(client: TestClient) -> None:
    r = client.get("/api/v1/sessions")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 3

    by_id = {s["session_id"]: s for s in body}
    assert set(by_id) == {"bahrain_2024_R", "monaco_2024_R", "hungary_2024_R"}


def test_round_numbers_match_2024_calendar(client: TestClient) -> None:
    r = client.get("/api/v1/sessions")
    by_id = {s["session_id"]: s for s in r.json()}
    assert by_id["bahrain_2024_R"]["round_number"] == 1
    assert by_id["monaco_2024_R"]["round_number"] == 8
    assert by_id["hungary_2024_R"]["round_number"] == 13


def test_session_summary_shape(client: TestClient) -> None:
    r = client.get("/api/v1/sessions")
    one = next(s for s in r.json() if s["session_id"] == "monaco_2024_R")
    assert set(one) == {
        "session_id",
        "circuit_id",
        "season",
        "round_number",
        "date",
        "total_laps",
    }
    assert one["circuit_id"] == "monaco"
    assert one["season"] == 2024
    assert one["date"] == "2024-05-26"
    assert one["total_laps"] == 78


# --------------------------------------------------------------------------
# Dependency override — empty repo
# --------------------------------------------------------------------------


def test_empty_repository_returns_empty_list() -> None:
    app = create_app()
    app.dependency_overrides[get_session_repository] = (
        lambda: InMemorySessionRepository(sessions=())
    )
    with TestClient(app) as client:
        r = client.get("/api/v1/sessions")
    assert r.status_code == 200
    assert r.json() == []


# --------------------------------------------------------------------------
# Dependency override — custom fixture
# --------------------------------------------------------------------------


def test_custom_repository_round_trips_through_route() -> None:
    custom = (
        SessionRow(
            session_id="spa_2024_R",
            circuit_id="spa",
            season=2024,
            round_number=14,
            date=date(2024, 7, 28),
            total_laps=44,
        ),
    )
    app = create_app()
    app.dependency_overrides[get_session_repository] = (
        lambda: InMemorySessionRepository(sessions=custom)
    )
    with TestClient(app) as client:
        r = client.get("/api/v1/sessions")
    assert r.status_code == 200
    assert r.json() == [
        {
            "session_id": "spa_2024_R",
            "circuit_id": "spa",
            "season": 2024,
            "round_number": 14,
            "date": "2024-07-28",
            "total_laps": 44,
        }
    ]
