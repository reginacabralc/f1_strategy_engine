"""Tests for clean-air degradation dataset preparation."""

from __future__ import annotations

from pitwall.degradation.dataset import (
    DEMO_SESSION_IDS,
    build_clean_lap_records,
    eligibility_for_lap,
)


def base_lap(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "session_id": "monaco_2024_R",
        "circuit_id": "monaco",
        "driver_code": "LEC",
        "team_code": "ferrari",
        "compound": "MEDIUM",
        "tyre_age": 5,
        "lap_number": 10,
        "stint_number": 1,
        "lap_time_ms": 78_500,
        "track_status": "GREEN",
        "is_pit_in_lap": False,
        "is_pit_out_lap": False,
        "is_deleted": False,
    }
    row.update(overrides)
    return row


def test_eligibility_accepts_clean_green_dry_lap() -> None:
    eligible, reason = eligibility_for_lap(base_lap())

    assert eligible is True
    assert reason is None


def test_eligibility_explains_excluded_rows() -> None:
    cases: list[tuple[dict[str, object], str]] = [
        ({"lap_time_ms": None}, "missing_lap_time"),
        ({"compound": "INTER"}, "unsupported_compound"),
        ({"tyre_age": None}, "missing_tyre_age"),
        ({"tyre_age": 0}, "tyre_age_lt_1"),
        ({"is_pit_in_lap": True}, "pit_in_lap"),
        ({"is_pit_out_lap": True}, "pit_out_lap"),
        ({"is_deleted": True}, "deleted_lap"),
        ({"track_status": "SC"}, "non_green_track_status"),
        ({"lap_time_ms": 250_000}, "invalid_lap_time"),
    ]

    for overrides, reason in cases:
        eligible, actual_reason = eligibility_for_lap(base_lap(**overrides))
        assert eligible is False
        assert actual_reason == reason


def test_build_clean_lap_records_preserves_excluded_rows_for_diagnostics() -> None:
    rows = build_clean_lap_records(
        [
            base_lap(lap_number=1),
            base_lap(lap_number=2, is_pit_out_lap=True),
            base_lap(lap_number=3, track_status="VSC"),
        ]
    )

    assert [row["fitting_eligible"] for row in rows] == [True, False, False]
    assert rows[1]["exclusion_reason"] == "pit_out_lap"
    assert rows[2]["exclusion_reason"] == "non_green_track_status"
    assert rows[2]["driver_code"] == "LEC"


def test_demo_session_ids_are_stable_for_day3_data() -> None:
    assert DEMO_SESSION_IDS == ("bahrain_2024_R", "monaco_2024_R", "hungarian_2024_R")
