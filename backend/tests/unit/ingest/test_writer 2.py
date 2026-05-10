"""Tests for ingestion writer payload preparation."""

from __future__ import annotations

from math import nan
from typing import Any

import polars as pl

from pitwall.ingest.writer import (
    INSERT_ORDER,
    ProcessedFileWriter,
    build_db_payloads,
    write_payloads_to_database,
)


def sample_outputs() -> dict[str, Any]:
    return {
        "metadata": {
            "session_id": "bahrain_2024_R",
            "year": 2024,
            "round": 1,
            "session": "R",
            "event_name": "Bahrain Grand Prix",
            "location": "Bahrain",
            "country": "Bahrain",
            "date": "2024-03-02",
            "total_laps": 57,
        },
        "drivers": [
            {
                "session_id": "bahrain_2024_R",
                "driver_code": "VER",
                "full_name": "Max Verstappen",
                "team_name": "Red Bull Racing",
            }
        ],
        "laps": [
            {
                "session_id": "bahrain_2024_R",
                "driver_code": "VER",
                "lap_number": 1,
                "lap_time_ms": nan,
                "sector_1_ms": None,
                "sector_2_ms": None,
                "sector_3_ms": None,
                "compound": "SOFT",
                "tyre_age": 1,
                "position": 1,
                "is_pit_in_lap": False,
                "is_pit_out_lap": True,
                "is_deleted": False,
                "track_status": "GREEN",
                "ts": "2024-03-02T15:05:00+00:00",
            }
        ],
        "pit_stops": [],
        "stints": [
            {
                "session_id": "bahrain_2024_R",
                "driver_code": "VER",
                "stint_number": 1,
                "compound": "SOFT",
                "lap_start": 1,
                "lap_end": 1,
                "age_at_start": 1,
            }
        ],
        "weather": [],
    }


def test_build_db_payloads_derives_reference_rows_and_cleans_nulls() -> None:
    payloads = build_db_payloads(sample_outputs())

    assert payloads["seasons"] == [{"season": 2024, "regulations": None}]
    assert payloads["circuits"][0]["circuit_id"] == "bahrain"
    assert payloads["events"][0]["event_id"] == "bahrain_2024"
    assert payloads["sessions"][0]["session_id"] == "bahrain_2024_R"
    assert payloads["teams"][0]["team_code"] == "red_bull_racing"
    assert payloads["drivers"][0]["team_code"] == "red_bull_racing"

    lap = payloads["laps"][0]
    assert lap["lap_time_ms"] is None
    assert lap["is_pit_in"] is False
    assert lap["is_pit_out"] is True
    assert lap["is_valid"] is True


def test_insert_order_respects_foreign_keys() -> None:
    assert INSERT_ORDER[:6] == [
        "seasons",
        "circuits",
        "events",
        "sessions",
        "teams",
        "drivers",
    ]
    assert INSERT_ORDER[6:] == [
        "laps",
        "pit_stops",
        "stints",
        "weather",
        "track_status_events",
    ]


def test_dry_run_writer_still_writes_parquet_outputs(tmp_path: Any) -> None:
    summary = ProcessedFileWriter(tmp_path).write_session("bahrain_2024_R", sample_outputs())

    assert summary.counts["laps"] == 1
    assert summary.output_dir is not None
    assert (summary.output_dir / "metadata.json").exists()
    assert pl.read_parquet(summary.output_dir / "laps.parquet").height == 1


class FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[dict[str, object]]]] = []

    def execute(self, statement: object, rows: list[dict[str, object]] | None = None) -> None:
        table_name = str(statement).split()[2]
        self.calls.append((table_name, rows or []))


def test_database_writer_uses_ordered_payloads_with_mock_connection() -> None:
    connection = FakeConnection()
    payloads = build_db_payloads(sample_outputs())

    write_payloads_to_database(connection, payloads)

    written_tables = [table for table, rows in connection.calls if rows]
    assert written_tables[:6] == INSERT_ORDER[:6]
