from __future__ import annotations

import pytest

from pitwall.ml.dataset import (
    FEATURE_COLUMNS,
    TARGET_COLUMN,
    build_loro_dataset,
    build_loro_folds,
    compute_reference_pace,
    validate_dataset_rows,
)


def _lap(
    session_id: str,
    circuit_id: str,
    driver_code: str,
    compound: str,
    lap_time_ms: int,
    *,
    lap_number: int = 1,
    tyre_age: int = 3,
    gap_to_ahead_ms: int | None = 2500,
    is_valid: bool = True,
    is_pit_in_lap: bool = False,
    is_pit_out_lap: bool = False,
    is_deleted: bool = False,
    track_status: str | None = "GREEN",
    total_laps: int = 60,
) -> dict[str, object]:
    return {
        "session_id": session_id,
        "circuit_id": circuit_id,
        "driver_code": driver_code,
        "team_code": "ferrari" if driver_code == "LEC" else "red_bull_racing",
        "compound": compound,
        "tyre_age": tyre_age,
        "lap_number": lap_number,
        "stint_number": 1,
        "lap_time_ms": lap_time_ms,
        "track_status": track_status,
        "is_pit_in_lap": is_pit_in_lap,
        "is_pit_out_lap": is_pit_out_lap,
        "is_deleted": is_deleted,
        "is_valid": is_valid,
        "total_laps": total_laps,
        "position": 1,
        "gap_to_ahead_ms": gap_to_ahead_ms,
        "gap_to_leader_ms": 0,
        "track_temp_c": 42.0,
        "air_temp_c": 26.0,
        "lap_in_stint": lap_number,
        "lap_in_stint_ratio": lap_number / total_laps,
    }


def test_reference_pace_uses_median_by_circuit_and_compound() -> None:
    rows = [
        _lap("bahrain_2024_R", "bahrain", "VER", "HARD", 90_000),
        _lap("bahrain_2024_R", "bahrain", "LEC", "HARD", 92_000),
        _lap("bahrain_2024_R", "bahrain", "VER", "HARD", 110_000),
    ]

    refs = compute_reference_pace(rows)

    assert refs.by_circuit_compound[("bahrain", "HARD")] == 92_000
    assert refs.by_compound["HARD"] == 92_000


def test_lap_time_delta_target_is_lap_time_minus_fold_safe_reference() -> None:
    rows = [
        _lap("bahrain_2024_R", "bahrain", "VER", "HARD", 90_000),
        _lap("bahrain_2024_R", "bahrain", "LEC", "HARD", 92_000),
        _lap("monaco_2024_R", "monaco", "VER", "HARD", 95_000),
    ]

    result = build_loro_dataset(rows)
    holdout = _only_row(result.rows, fold_id="fold_monaco_2024_R", session_id="monaco_2024_R")

    assert holdout["reference_source"] == "global_compound"
    assert holdout["reference_lap_time_ms"] == 91_000
    assert holdout[TARGET_COLUMN] == 4_000
    assert holdout["row_usable"] is True


def test_leave_one_race_out_folds_mark_train_and_holdout_sessions() -> None:
    folds = build_loro_folds(["bahrain_2024_R", "monaco_2024_R", "hungary_2024_R"])

    assert [fold.holdout_session_id for fold in folds] == [
        "bahrain_2024_R",
        "hungary_2024_R",
        "monaco_2024_R",
    ]
    assert "monaco_2024_R" not in folds[-1].train_session_ids


def test_driver_offsets_are_computed_from_training_sessions_only() -> None:
    rows = [
        _lap("bahrain_2024_R", "bahrain", "VER", "HARD", 90_000),
        _lap("bahrain_2024_R", "bahrain", "LEC", "HARD", 92_000),
        _lap("hungary_2024_R", "hungary", "VER", "HARD", 88_000),
        _lap("hungary_2024_R", "hungary", "LEC", "HARD", 92_000),
        _lap("monaco_2024_R", "monaco", "VER", "HARD", 140_000),
    ]

    result = build_loro_dataset(rows)
    holdout = _only_row(result.rows, fold_id="fold_monaco_2024_R", session_id="monaco_2024_R")

    assert holdout["driver_pace_offset_ms"] == -1_500
    assert holdout["driver_pace_offset_missing"] is False
    assert holdout["driver_offset_source"] == "driver_compound"
    assert holdout["driver_offset_source_sessions"] == "bahrain_2024_R,hungary_2024_R"


def test_traffic_proxy_features_use_gap_to_ahead() -> None:
    rows = [
        _lap("bahrain_2024_R", "bahrain", "VER", "HARD", 90_000, gap_to_ahead_ms=1200),
        _lap("monaco_2024_R", "monaco", "LEC", "HARD", 92_000, gap_to_ahead_ms=2600),
    ]

    result = build_loro_dataset(rows)
    row = _only_row(result.rows, fold_id="fold_monaco_2024_R", session_id="bahrain_2024_R")

    assert row["is_in_traffic"] is True
    assert row["dirty_air_proxy_ms"] == 800


def test_missing_reference_marks_row_unusable() -> None:
    rows = [
        _lap("bahrain_2024_R", "bahrain", "VER", "HARD", 90_000),
        _lap("monaco_2024_R", "monaco", "LEC", "SOFT", 82_000),
    ]

    result = build_loro_dataset(rows)
    holdout = _only_row(result.rows, fold_id="fold_monaco_2024_R", session_id="monaco_2024_R")

    assert holdout["row_usable"] is False
    assert holdout["missing_reason"] == "missing_reference"
    assert holdout[TARGET_COLUMN] is None


def test_clean_lap_filtering_keeps_dry_green_valid_non_pit_laps_only() -> None:
    rows = [
        _lap("bahrain_2024_R", "bahrain", "VER", "HARD", 90_000),
        _lap("bahrain_2024_R", "bahrain", "VER", "INTER", 90_000),
        _lap("bahrain_2024_R", "bahrain", "VER", "HARD", 90_000, is_pit_in_lap=True),
        _lap("bahrain_2024_R", "bahrain", "VER", "HARD", 90_000, track_status="SC"),
        _lap("monaco_2024_R", "monaco", "LEC", "HARD", 92_000),
    ]

    result = build_loro_dataset(rows)

    assert {row["compound"] for row in result.rows} == {"HARD"}
    assert all(row["track_status"] == "GREEN" for row in result.rows)
    assert all(row["is_pit_in_lap"] is False for row in result.rows)


def test_validation_rejects_pit_loss_leakage() -> None:
    rows = [
        {
            column: 0
            for column in [
                *FEATURE_COLUMNS,
                TARGET_COLUMN,
                "row_usable",
                "compound",
                "split",
                "session_id",
                "fold_id",
            ]
        }
    ]
    rows[0]["pit_loss_ms"] = 21_000

    with pytest.raises(ValueError, match="pit_loss"):
        validate_dataset_rows(rows, metadata={"folds": []})


def _only_row(
    rows: list[dict[str, object]],
    *,
    fold_id: str,
    session_id: str,
) -> dict[str, object]:
    matches = [
        row
        for row in rows
        if row["fold_id"] == fold_id and row["session_id"] == session_id
    ]
    assert len(matches) == 1
    return matches[0]
