"""SQL-backed repositories for Stream A/B integration."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from importlib import import_module
from typing import Any, Protocol, cast

from pitwall.feeds.base import Event
from pitwall.repositories.sessions import SessionRow

SESSION_SQL = """
    SELECT
        s.session_id,
        e.circuit_id,
        e.season,
        e.round_number,
        s.date,
        s.total_laps
    FROM sessions s
    JOIN events e ON e.event_id = s.event_id
    ORDER BY e.season, e.round_number, s.session_type
"""

SESSION_METADATA_SQL = """
    /* SESSION_METADATA */
    SELECT
        s.session_id,
        e.circuit_id,
        s.total_laps,
        ARRAY_AGG(DISTINCT l.driver_code ORDER BY l.driver_code) AS drivers,
        MIN(l.ts) AS first_ts,
        MAX(l.ts) AS last_ts
    FROM sessions s
    JOIN events e ON e.event_id = s.event_id
    LEFT JOIN laps l ON l.session_id = s.session_id
    WHERE s.session_id = :session_id
    GROUP BY s.session_id, e.circuit_id, s.total_laps
"""

LAP_EVENTS_SQL = """
    /* LAP_EVENTS */
    SELECT
        session_id,
        driver_code,
        lap_number,
        lap_time_ms,
        sector_1_ms,
        sector_2_ms,
        sector_3_ms,
        compound,
        tyre_age,
        is_pit_in,
        is_pit_out,
        is_valid,
        track_status,
        position,
        gap_to_leader_ms,
        gap_to_ahead_ms,
        ts
    FROM laps
    WHERE session_id = :session_id
    ORDER BY ts, lap_number, position NULLS LAST, driver_code
"""

WEATHER_EVENTS_SQL = """
    /* WEATHER_EVENTS */
    SELECT
        session_id,
        ts,
        track_temp_c,
        air_temp_c,
        humidity_pct,
        rainfall
    FROM weather
    WHERE session_id = :session_id
    ORDER BY ts
"""


class EngineLike(Protocol):
    def connect(self) -> Any:
        ...


class SqlSessionRepository:
    """Read sessions from the local Postgres/TimescaleDB schema."""

    def __init__(self, engine: EngineLike) -> None:
        self.engine = engine

    async def list_sessions(self) -> list[SessionRow]:
        with self.engine.connect() as connection:
            rows = connection.execute(_sql_text(SESSION_SQL))
            return [
                SessionRow(
                    session_id=str(row._mapping["session_id"]),
                    circuit_id=str(row._mapping["circuit_id"]),
                    season=int(row._mapping["season"]),
                    round_number=int(row._mapping["round_number"]),
                    date=row._mapping["date"],
                    total_laps=(
                        int(row._mapping["total_laps"])
                        if row._mapping["total_laps"] is not None
                        else None
                    ),
                )
                for row in rows
            ]


class SqlSessionEventLoader:
    """Load replay events from Stream A's ingested DB tables."""

    def __init__(self, engine: EngineLike) -> None:
        self.engine = engine

    async def load_events(self, session_id: str) -> list[Event]:
        with self.engine.connect() as connection:
            metadata_rows = list(
                connection.execute(_sql_text(SESSION_METADATA_SQL), {"session_id": session_id})
            )
            if not metadata_rows:
                return []
            metadata = dict(metadata_rows[0]._mapping)
            if metadata.get("first_ts") is None:
                return []

            events = [self._session_start_event(metadata)]
            events.extend(
                self._lap_event(dict(row._mapping))
                for row in connection.execute(_sql_text(LAP_EVENTS_SQL), {"session_id": session_id})
            )
            events.extend(
                self._weather_event(dict(row._mapping))
                for row in connection.execute(
                    _sql_text(WEATHER_EVENTS_SQL),
                    {"session_id": session_id},
                )
            )
        return sorted(events, key=_event_sort_key)

    def _session_start_event(self, metadata: dict[str, Any]) -> Event:
        return {
            "type": "session_start",
            "session_id": str(metadata["session_id"]),
            "ts": cast(datetime, metadata["first_ts"]),
            "payload": {
                "circuit_id": metadata["circuit_id"],
                "total_laps": metadata["total_laps"],
                "drivers": list(cast(Iterable[str], metadata.get("drivers") or [])),
            },
        }

    def _lap_event(self, row: dict[str, Any]) -> Event:
        return {
            "type": "lap_complete",
            "session_id": str(row["session_id"]),
            "ts": cast(datetime, row["ts"]),
            "payload": {
                "driver_code": row["driver_code"],
                "lap_number": row["lap_number"],
                "lap_time_ms": row["lap_time_ms"],
                "sector_1_ms": row["sector_1_ms"],
                "sector_2_ms": row["sector_2_ms"],
                "sector_3_ms": row["sector_3_ms"],
                "compound": row["compound"],
                "tyre_age": row["tyre_age"],
                "is_pit_in": row["is_pit_in"],
                "is_pit_out": row["is_pit_out"],
                "is_valid": row["is_valid"],
                "track_status": row["track_status"],
                "position": row["position"],
                "gap_to_leader_ms": row["gap_to_leader_ms"],
                "gap_to_ahead_ms": row["gap_to_ahead_ms"],
            },
        }

    def _weather_event(self, row: dict[str, Any]) -> Event:
        return {
            "type": "weather_update",
            "session_id": str(row["session_id"]),
            "ts": cast(datetime, row["ts"]),
            "payload": {
                "track_temp_c": row["track_temp_c"],
                "air_temp_c": row["air_temp_c"],
                "humidity_pct": row["humidity_pct"],
                "rainfall": row["rainfall"],
            },
        }


def _event_order(event_type: str) -> int:
    return {
        "session_start": 0,
        "track_status_change": 1,
        "weather_update": 2,
        "lap_complete": 3,
        "session_end": 9,
    }.get(event_type, 5)


def _event_sort_key(event: Event) -> tuple[int, datetime, int]:
    return (
        0 if event["type"] == "session_start" else 1,
        event["ts"],
        _event_order(event["type"]),
    )


def _sql_text(sql: str) -> Any:
    sqlalchemy = import_module("sqlalchemy")
    return sqlalchemy.text(sql)
