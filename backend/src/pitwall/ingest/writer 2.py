"""Writer layer for normalized ingestion outputs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol

from pitwall.ingest.normalize import circuit_slug, clean_nulls, slugify, to_bool

INSERT_ORDER = [
    "seasons",
    "circuits",
    "events",
    "sessions",
    "teams",
    "drivers",
    "laps",
    "pit_stops",
    "stints",
    "weather",
    "track_status_events",
]

UPSERT_SQL = {
    "seasons": """
        INSERT INTO seasons (season, regulations)
        VALUES (:season, :regulations)
        ON CONFLICT (season) DO UPDATE SET regulations = EXCLUDED.regulations
    """,
    "circuits": """
        INSERT INTO circuits (
            circuit_id, name, country, pit_lane_loss_seconds,
            pit_lane_speed_limit, typical_race_laps
        )
        VALUES (
            :circuit_id, :name, :country, :pit_lane_loss_seconds,
            :pit_lane_speed_limit, :typical_race_laps
        )
        ON CONFLICT (circuit_id) DO UPDATE SET
            name = EXCLUDED.name,
            country = EXCLUDED.country,
            pit_lane_loss_seconds = EXCLUDED.pit_lane_loss_seconds,
            pit_lane_speed_limit = EXCLUDED.pit_lane_speed_limit,
            typical_race_laps = EXCLUDED.typical_race_laps
    """,
    "events": """
        INSERT INTO events (event_id, season, circuit_id, round_number, name, start_date)
        VALUES (:event_id, :season, :circuit_id, :round_number, :name, :start_date)
        ON CONFLICT (event_id) DO UPDATE SET
            season = EXCLUDED.season,
            circuit_id = EXCLUDED.circuit_id,
            round_number = EXCLUDED.round_number,
            name = EXCLUDED.name,
            start_date = EXCLUDED.start_date
    """,
    "sessions": """
        INSERT INTO sessions (session_id, event_id, session_type, date, total_laps)
        VALUES (:session_id, :event_id, :session_type, :date, :total_laps)
        ON CONFLICT (session_id) DO UPDATE SET
            event_id = EXCLUDED.event_id,
            session_type = EXCLUDED.session_type,
            date = EXCLUDED.date,
            total_laps = EXCLUDED.total_laps
    """,
    "teams": """
        INSERT INTO teams (team_code, full_name)
        VALUES (:team_code, :full_name)
        ON CONFLICT (team_code) DO UPDATE SET full_name = EXCLUDED.full_name
    """,
    "drivers": """
        INSERT INTO drivers (driver_code, full_name, team_code)
        VALUES (:driver_code, :full_name, :team_code)
        ON CONFLICT (driver_code) DO UPDATE SET
            full_name = EXCLUDED.full_name,
            team_code = EXCLUDED.team_code
    """,
    "laps": """
        INSERT INTO laps (
            session_id, driver_code, lap_number, lap_time_ms, sector_1_ms,
            sector_2_ms, sector_3_ms, compound, tyre_age, is_pit_in,
            is_pit_out, is_valid, track_status, position, gap_to_leader_ms,
            gap_to_ahead_ms, ts
        )
        VALUES (
            :session_id, :driver_code, :lap_number, :lap_time_ms, :sector_1_ms,
            :sector_2_ms, :sector_3_ms, :compound, :tyre_age, :is_pit_in,
            :is_pit_out, :is_valid, :track_status, :position, :gap_to_leader_ms,
            :gap_to_ahead_ms, :ts
        )
        ON CONFLICT (session_id, driver_code, lap_number, ts) DO UPDATE SET
            lap_time_ms = EXCLUDED.lap_time_ms,
            sector_1_ms = EXCLUDED.sector_1_ms,
            sector_2_ms = EXCLUDED.sector_2_ms,
            sector_3_ms = EXCLUDED.sector_3_ms,
            compound = EXCLUDED.compound,
            tyre_age = EXCLUDED.tyre_age,
            is_pit_in = EXCLUDED.is_pit_in,
            is_pit_out = EXCLUDED.is_pit_out,
            is_valid = EXCLUDED.is_valid,
            track_status = EXCLUDED.track_status,
            position = EXCLUDED.position,
            gap_to_leader_ms = EXCLUDED.gap_to_leader_ms,
            gap_to_ahead_ms = EXCLUDED.gap_to_ahead_ms
    """,
    "pit_stops": """
        INSERT INTO pit_stops (
            session_id, driver_code, lap_number, duration_ms, pit_loss_ms,
            new_compound, ts
        )
        VALUES (
            :session_id, :driver_code, :lap_number, :duration_ms, :pit_loss_ms,
            :new_compound, :ts
        )
        ON CONFLICT (session_id, driver_code, lap_number) DO UPDATE SET
            duration_ms = EXCLUDED.duration_ms,
            pit_loss_ms = EXCLUDED.pit_loss_ms,
            new_compound = EXCLUDED.new_compound,
            ts = EXCLUDED.ts
    """,
    "stints": """
        INSERT INTO stints (
            session_id, driver_code, stint_number, compound, lap_start,
            lap_end, age_at_start
        )
        VALUES (
            :session_id, :driver_code, :stint_number, :compound, :lap_start,
            :lap_end, :age_at_start
        )
        ON CONFLICT (session_id, driver_code, stint_number) DO UPDATE SET
            compound = EXCLUDED.compound,
            lap_start = EXCLUDED.lap_start,
            lap_end = EXCLUDED.lap_end,
            age_at_start = EXCLUDED.age_at_start
    """,
    "weather": """
        INSERT INTO weather (
            session_id, ts, lap_number, track_temp_c, air_temp_c,
            humidity_pct, rainfall
        )
        VALUES (
            :session_id, :ts, :lap_number, :track_temp_c, :air_temp_c,
            :humidity_pct, :rainfall
        )
        ON CONFLICT (session_id, ts) DO UPDATE SET
            lap_number = EXCLUDED.lap_number,
            track_temp_c = EXCLUDED.track_temp_c,
            air_temp_c = EXCLUDED.air_temp_c,
            humidity_pct = EXCLUDED.humidity_pct,
            rainfall = EXCLUDED.rainfall
    """,
    "track_status_events": """
        INSERT INTO track_status_events (
            session_id, started_ts, ended_ts, lap_number, status
        )
        VALUES (
            :session_id, :started_ts, :ended_ts, :lap_number, :status
        )
        ON CONFLICT (session_id, started_ts) DO UPDATE SET
            ended_ts = EXCLUDED.ended_ts,
            lap_number = EXCLUDED.lap_number,
            status = EXCLUDED.status
    """,
}


class DatabaseConnection(Protocol):
    def execute(self, statement: object, parameters: list[dict[str, Any]] | None = None) -> Any:
        ...

@dataclass(frozen=True, slots=True)
class WriteSummary:
    output_dir: Path | None
    counts: dict[str, int]
    destination: str = "files"


class ProcessedFileWriter:
    """Write normalized records under ``data/processed/<session_id>/``."""

    def __init__(self, base_dir: Path = Path("data/processed")) -> None:
        self.base_dir = base_dir

    def write_session(self, session_id: str, outputs: dict[str, Any]) -> WriteSummary:
        output_dir = self.base_dir / session_id
        output_dir.mkdir(parents=True, exist_ok=True)

        counts: dict[str, int] = {}
        for name in ("laps", "stints", "drivers", "pit_stops", "weather"):
            records = list(outputs.get(name, []))
            counts[name] = len(records)
            self._write_records(output_dir / f"{name}.parquet", records)

        metadata = outputs.get("metadata", {})
        (output_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        counts["metadata"] = 1 if metadata else 0
        return WriteSummary(output_dir=output_dir, counts=counts)

    def _write_records(self, path: Path, records: list[dict[str, Any]]) -> None:
        try:
            import polars as pl
        except ImportError as exc:  # pragma: no cover - exercised by CLI users.
            raise RuntimeError(
                "Polars is required to write parquet outputs. Install backend dependencies first."
            ) from exc

        frame = pl.DataFrame(records) if records else pl.DataFrame()
        frame.write_parquet(path)


class DatabaseWriter:
    """Write normalized records to the local Postgres/TimescaleDB schema."""

    def __init__(self, engine: Any) -> None:
        self.engine = engine

    def write_session(self, outputs: dict[str, Any]) -> WriteSummary:
        payloads = build_db_payloads(outputs)
        with self.engine.begin() as connection:
            write_payloads_to_database(connection, payloads)
            connection.execute(_sql_text("REFRESH MATERIALIZED VIEW clean_air_lap_times"))
        return WriteSummary(
            output_dir=None,
            counts={table: len(rows) for table, rows in payloads.items()},
            destination="database",
        )


def build_db_payloads(outputs: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Build FK-ordered DB payloads from Day 2 normalized outputs."""

    metadata = dict(clean_nulls(outputs.get("metadata", {})))
    if not metadata:
        raise ValueError("metadata is required for database ingestion")

    year = int(metadata["year"])
    circuit_id = _metadata_circuit_id(metadata)
    event_id = _metadata_event_id(metadata, circuit_id)
    session_id = str(metadata["session_id"])
    session_date = str(metadata.get("date") or f"{year}-01-01")

    drivers = [dict(clean_nulls(row)) for row in outputs.get("drivers", [])]
    teams_by_code = _teams_from_drivers(drivers)

    payloads: dict[str, list[dict[str, Any]]] = {
        "seasons": [{"season": year, "regulations": None}],
        "circuits": [
            {
                "circuit_id": circuit_id,
                "name": metadata.get("location") or metadata.get("event_name") or circuit_id,
                "country": metadata.get("country"),
                "pit_lane_loss_seconds": None,
                "pit_lane_speed_limit": None,
                "typical_race_laps": metadata.get("total_laps"),
            }
        ],
        "events": [
            {
                "event_id": event_id,
                "season": year,
                "circuit_id": circuit_id,
                "round_number": metadata["round"],
                "name": metadata.get("event_name") or circuit_id,
                "start_date": session_date,
            }
        ],
        "sessions": [
            {
                "session_id": session_id,
                "event_id": event_id,
                "session_type": metadata["session"],
                "date": session_date,
                "total_laps": metadata.get("total_laps"),
            }
        ],
        "teams": list(teams_by_code.values()),
        "drivers": [_driver_row(driver) for driver in drivers],
        "laps": [_lap_row(row) for row in outputs.get("laps", [])],
        "pit_stops": [_pit_stop_row(row) for row in outputs.get("pit_stops", [])],
        "stints": [dict(clean_nulls(row)) for row in outputs.get("stints", [])],
        "weather": [dict(clean_nulls(row)) for row in outputs.get("weather", [])],
        "track_status_events": [
            dict(clean_nulls(row)) for row in outputs.get("track_status_events", [])
        ],
    }
    return payloads


def write_payloads_to_database(
    connection: DatabaseConnection,
    payloads: dict[str, list[dict[str, Any]]],
) -> None:
    """Insert payloads in FK-safe order using idempotent upserts."""

    for table_name in INSERT_ORDER:
        rows = payloads.get(table_name, [])
        if not rows:
            continue
        connection.execute(_sql_text(UPSERT_SQL[table_name]), rows)


def _metadata_circuit_id(metadata: dict[str, Any]) -> str:
    value = metadata.get("event_name") or metadata.get("location") or metadata["session_id"]
    return circuit_slug(str(value))


def _metadata_event_id(metadata: dict[str, Any], circuit_id: str) -> str:
    return f"{circuit_id}_{metadata['year']}"


def _teams_from_drivers(drivers: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    teams: dict[str, dict[str, Any]] = {}
    for driver in drivers:
        team_name = driver.get("team_name")
        if not team_name:
            continue
        team_code = slugify(str(team_name))
        teams[team_code] = {"team_code": team_code, "full_name": team_name}
    return teams


def _driver_row(driver: dict[str, Any]) -> dict[str, Any]:
    team_name = driver.get("team_name")
    return {
        "driver_code": driver["driver_code"],
        "full_name": driver.get("full_name"),
        "team_code": slugify(str(team_name)) if team_name else None,
    }


def _lap_row(row: Any) -> dict[str, Any]:
    lap = dict(clean_nulls(row))
    if lap.get("ts") is None:
        raise ValueError(
            f"lap row is missing ts: {lap.get('session_id')} {lap.get('driver_code')} "
            f"lap {lap.get('lap_number')}"
        )
    return {
        "session_id": lap["session_id"],
        "driver_code": lap["driver_code"],
        "lap_number": lap["lap_number"],
        "lap_time_ms": lap.get("lap_time_ms"),
        "sector_1_ms": lap.get("sector_1_ms"),
        "sector_2_ms": lap.get("sector_2_ms"),
        "sector_3_ms": lap.get("sector_3_ms"),
        "compound": lap.get("compound"),
        "tyre_age": lap.get("tyre_age"),
        "is_pit_in": to_bool(lap.get("is_pit_in_lap")),
        "is_pit_out": to_bool(lap.get("is_pit_out_lap")),
        "is_valid": not to_bool(lap.get("is_deleted")),
        "track_status": lap.get("track_status"),
        "position": lap.get("position"),
        "gap_to_leader_ms": lap.get("gap_to_leader_ms"),
        "gap_to_ahead_ms": lap.get("gap_to_ahead_ms"),
        "ts": lap["ts"],
    }


def _pit_stop_row(row: Any) -> dict[str, Any]:
    pit_stop = dict(clean_nulls(row))
    if pit_stop.get("ts") is None:
        raise ValueError(
            f"pit stop row is missing ts: {pit_stop.get('session_id')} "
            f"{pit_stop.get('driver_code')} lap {pit_stop.get('lap_number')}"
        )
    return {
        "session_id": pit_stop["session_id"],
        "driver_code": pit_stop["driver_code"],
        "lap_number": pit_stop["lap_number"],
        "duration_ms": pit_stop.get("duration_ms"),
        "pit_loss_ms": pit_stop.get("pit_loss_ms"),
        "new_compound": pit_stop.get("new_compound"),
        "ts": pit_stop["ts"],
    }


def _sql_text(sql: str) -> Any:
    sqlalchemy = import_module("sqlalchemy")
    return sqlalchemy.text(sql)
