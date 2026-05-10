"""Unit tests for FastF1 normalization.

These tests use tiny synthetic records so they never download FastF1 data.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import nan

from pitwall.ingest.normalize import (
    build_session_id,
    clean_nulls,
    normalize_laps,
    reconstruct_stints,
    timedelta_to_ms,
)


def test_timedelta_to_ms_converts_whole_milliseconds() -> None:
    assert timedelta_to_ms(timedelta(seconds=1, milliseconds=234)) == 1234
    assert timedelta_to_ms(None) is None


def test_clean_nulls_converts_nan_to_none_recursively() -> None:
    cleaned = clean_nulls(
        {
            "driver_code": "LEC",
            "lap_time_ms": nan,
            "nested": {"track_status": nan},
            "list": [1, nan],
        }
    )

    assert cleaned == {
        "driver_code": "LEC",
        "lap_time_ms": None,
        "nested": {"track_status": None},
        "list": [1, None],
    }


def test_build_session_id_prefers_event_location() -> None:
    assert build_session_id({"Location": "Monaco"}, year=2024, session_code="R") == "monaco_2024_R"


def test_normalize_laps_preserves_pit_and_deleted_flags() -> None:
    rows = normalize_laps(
        [
            {
                "Driver": "LEC",
                "LapNumber": 1,
                "LapTime": timedelta(minutes=1, seconds=18, milliseconds=450),
                "Compound": "MEDIUM",
                "TyreLife": 4,
                "Stint": 1,
                "Position": 1,
                "PitInTime": None,
                "PitOutTime": timedelta(minutes=2),
                "Deleted": False,
                "TrackStatus": "1",
                "Time": timedelta(minutes=2),
            },
            {
                "Driver": "LEC",
                "LapNumber": 2,
                "LapTime": nan,
                "Compound": "MEDIUM",
                "TyreLife": 5,
                "Stint": 1,
                "Position": 1,
                "PitInTime": timedelta(minutes=3),
                "PitOutTime": None,
                "Deleted": True,
                "TrackStatus": "4",
                "Time": timedelta(minutes=3),
            },
        ],
        session_id="monaco_2024_R",
        session_start=datetime(2024, 5, 26, 13, 0, tzinfo=UTC),
    )

    assert rows[0]["lap_time_ms"] == 78_450
    assert rows[0]["is_pit_out_lap"] is True
    assert rows[0]["is_pit_in_lap"] is False
    assert rows[0]["is_deleted"] is False
    assert rows[0]["track_status"] == "GREEN"
    assert rows[0]["ts"] == "2024-05-26T13:02:00+00:00"

    assert rows[1]["lap_time_ms"] is None
    assert rows[1]["is_pit_in_lap"] is True
    assert rows[1]["is_deleted"] is True
    assert rows[1]["track_status"] == "SC"


def test_reconstruct_stints_uses_stint_number_when_available() -> None:
    stints = reconstruct_stints(
        [
            {
                "session_id": "monaco_2024_R",
                "driver_code": "LEC",
                "lap_number": 1,
                "compound": "MEDIUM",
                "tyre_age": 4,
                "stint_number": 1,
            },
            {
                "session_id": "monaco_2024_R",
                "driver_code": "LEC",
                "lap_number": 2,
                "compound": "MEDIUM",
                "tyre_age": 5,
                "stint_number": 1,
            },
            {
                "session_id": "monaco_2024_R",
                "driver_code": "LEC",
                "lap_number": 3,
                "compound": "HARD",
                "tyre_age": 1,
                "stint_number": 2,
            },
        ]
    )

    assert stints == [
        {
            "session_id": "monaco_2024_R",
            "driver_code": "LEC",
            "stint_number": 1,
            "compound": "MEDIUM",
            "lap_start": 1,
            "lap_end": 2,
            "age_at_start": 4,
        },
        {
            "session_id": "monaco_2024_R",
            "driver_code": "LEC",
            "stint_number": 2,
            "compound": "HARD",
            "lap_start": 3,
            "lap_end": 3,
            "age_at_start": 1,
        },
    ]


def test_reconstruct_stints_detects_compound_change_without_stint_number() -> None:
    stints = reconstruct_stints(
        [
            {
                "session_id": "monaco_2024_R",
                "driver_code": "NOR",
                "lap_number": 1,
                "compound": "MEDIUM",
                "tyre_age": 10,
            },
            {
                "session_id": "monaco_2024_R",
                "driver_code": "NOR",
                "lap_number": 2,
                "compound": "HARD",
                "tyre_age": 1,
                "is_pit_out_lap": True,
            },
        ]
    )

    assert [row["stint_number"] for row in stints] == [1, 2]
    assert [row["compound"] for row in stints] == ["MEDIUM", "HARD"]
