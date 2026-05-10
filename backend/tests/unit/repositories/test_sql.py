"""Tests for SQL-backed Stream A repository adapters."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Any

import pytest

from pitwall.repositories.sql import SqlSessionEventLoader, SqlSessionRepository


class FakeRow:
    def __init__(self, values: dict[str, Any]) -> None:
        self._mapping = values


class FakeConnection:
    def __init__(self, rows_by_marker: dict[str, list[dict[str, Any]]]) -> None:
        self.rows_by_marker = rows_by_marker

    def execute(self, statement: object, parameters: dict[str, Any] | None = None) -> list[FakeRow]:
        sql = str(statement)
        for marker, rows in self.rows_by_marker.items():
            if marker in sql:
                return [FakeRow(row) for row in rows]
        return []


class FakeEngine:
    def __init__(self, rows_by_marker: dict[str, list[dict[str, Any]]]) -> None:
        self.connection = FakeConnection(rows_by_marker)

    @contextmanager
    def connect(self) -> Iterator[FakeConnection]:
        yield self.connection


@pytest.mark.asyncio
async def test_sql_session_repository_lists_sessions() -> None:
    engine = FakeEngine(
        {
            "FROM sessions s": [
                {
                    "session_id": "monaco_2024_R",
                    "circuit_id": "monaco",
                    "season": 2024,
                    "round_number": 8,
                    "date": date(2024, 5, 26),
                    "total_laps": 78,
                }
            ]
        }
    )

    rows = await SqlSessionRepository(engine).list_sessions()

    assert rows[0].session_id == "monaco_2024_R"
    assert rows[0].circuit_id == "monaco"
    assert rows[0].round_number == 8


@pytest.mark.asyncio
async def test_sql_event_loader_builds_ordered_replay_events() -> None:
    t0 = datetime(2024, 5, 26, 13, 0, tzinfo=UTC)
    engine = FakeEngine(
        {
            "SESSION_METADATA": [
                {
                    "session_id": "monaco_2024_R",
                    "circuit_id": "monaco",
                    "total_laps": 78,
                    "drivers": ["LEC", "PIA"],
                    "first_ts": t0,
                    "last_ts": t0,
                }
            ],
            "LAP_EVENTS": [
                {
                    "session_id": "monaco_2024_R",
                    "driver_code": "LEC",
                    "lap_number": 1,
                    "lap_time_ms": 81_000,
                    "sector_1_ms": None,
                    "sector_2_ms": None,
                    "sector_3_ms": None,
                    "compound": "MEDIUM",
                    "tyre_age": 1,
                    "is_pit_in": False,
                    "is_pit_out": False,
                    "is_valid": True,
                    "track_status": "GREEN",
                    "position": 1,
                    "gap_to_leader_ms": 0,
                    "gap_to_ahead_ms": None,
                    "ts": t0,
                },
                {
                    "session_id": "monaco_2024_R",
                    "driver_code": "PIA",
                    "lap_number": 1,
                    "lap_time_ms": 82_000,
                    "sector_1_ms": None,
                    "sector_2_ms": None,
                    "sector_3_ms": None,
                    "compound": "MEDIUM",
                    "tyre_age": 1,
                    "is_pit_in": False,
                    "is_pit_out": False,
                    "is_valid": True,
                    "track_status": "GREEN",
                    "position": 2,
                    "gap_to_leader_ms": 1000,
                    "gap_to_ahead_ms": 1000,
                    "ts": t0,
                },
            ],
            "WEATHER_EVENTS": [],
        }
    )

    events = await SqlSessionEventLoader(engine).load_events("monaco_2024_R")

    assert [event["type"] for event in events] == [
        "session_start",
        "lap_complete",
        "lap_complete",
    ]
    assert events[0]["payload"] == {
        "circuit_id": "monaco",
        "total_laps": 78,
        "drivers": ["LEC", "PIA"],
    }
    assert events[1]["payload"]["driver_code"] == "LEC"


@pytest.mark.asyncio
async def test_sql_event_loader_returns_empty_for_unknown_session() -> None:
    engine = FakeEngine({"SESSION_METADATA": []})

    assert await SqlSessionEventLoader(engine).load_events("missing_2024_R") == []
