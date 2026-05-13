from __future__ import annotations

from pathlib import Path

import pytest

from pitwall.ml.dataset import (
    FEATURE_COLUMNS,
    TARGET_COLUMN,
    DatasetBuildResult,
    build_loro_dataset,
    build_loro_folds,
    build_temporal_expanding_dataset,
    build_temporal_expanding_folds,
    build_temporal_year_dataset,
    compute_reference_pace,
    validate_dataset_rows,
    write_dataset,
)


def _lap(
    session_id: str,
    circuit_id: str,
    driver_code: str,
    compound: str,
    lap_time_ms: int,
    *,
    season: int = 2024,
    round_number: int = 1,
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
        "season": season,
        "round_number": round_number,
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


def test_temporal_expanding_folds_use_only_past_sessions() -> None:
    sessions = [
        ("s1", 2024, 1),
        ("s2", 2024, 2),
        ("s3", 2024, 3),
        ("s4", 2024, 4),
        ("s5", 2025, 1),
        ("s6", 2025, 2),
    ]

    folds = build_temporal_expanding_folds(sessions, block_size=2)

    assert [(fold.train_session_ids, fold.validation_session_ids) for fold in folds] == [
        (("s1", "s2"), ("s3", "s4")),
        (("s1", "s2", "s3", "s4"), ("s5", "s6")),
    ]
    assert all(
        max(fold.train_event_orders) < min(fold.validation_event_orders)
        for fold in folds
    )


def test_temporal_dataset_marks_chronology_and_split_strategy() -> None:
    rows = [
        _lap("s1", "bahrain", "VER", "HARD", 90_000, season=2024, round_number=1),
        _lap("s2", "jeddah", "LEC", "HARD", 91_000, season=2024, round_number=2),
        _lap("s3", "melbourne", "VER", "HARD", 92_000, season=2024, round_number=3),
        _lap("s4", "suzuka", "LEC", "HARD", 93_000, season=2024, round_number=4),
    ]

    result = build_temporal_expanding_dataset(rows, block_size=2)

    assert result.metadata["split_strategy"] == "temporal_expanding"
    assert [row["event_order"] for row in result.metadata["session_chronology"]] == [1, 2, 3, 4]
    assert {row["split_strategy"] for row in result.rows} == {"temporal_expanding"}
    fold_rows = [row for row in result.rows if row["fold_id"] == "fold_001"]
    assert {row["split"] for row in fold_rows} == {"train", "validation"}
    assert {row["session_id"] for row in fold_rows if row["split"] == "train"} == {"s1", "s2"}
    assert {row["session_id"] for row in fold_rows if row["split"] == "validation"} == {"s3", "s4"}


def test_temporal_year_dataset_supports_train_validation_and_test_years() -> None:
    rows = [
        _lap("s1", "bahrain", "VER", "HARD", 90_000, season=2024, round_number=1),
        _lap("s2", "melbourne", "LEC", "HARD", 91_000, season=2025, round_number=1),
        _lap("s3", "miami", "VER", "HARD", 92_000, season=2026, round_number=1),
    ]

    result = build_temporal_year_dataset(
        rows,
        train_years=(2024,),
        validation_years=(2025,),
        test_years=(2026,),
    )

    assert result.metadata["split_strategy"] == "temporal_year"
    assert result.metadata["final_test_status"] == "reserved"
    assert {row["split"] for row in result.rows} == {"train", "validation", "test"}


def test_validation_rejects_temporal_future_leakage() -> None:
    rows: list[dict[str, object]] = [
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
                "season",
                "round_number",
                "event_order",
                "split_strategy",
            ]
        }
    ]
    rows[0]["compound"] = "HARD"
    rows[0]["split"] = "train"
    rows[0]["event_order"] = 3
    rows.append({**rows[0], "split": "validation", "event_order": 2})

    with pytest.raises(ValueError, match="future session"):
        validate_dataset_rows(
            rows,
            metadata={
                "split_strategy": "temporal_expanding",
                "folds": [
                    {
                        "fold_id": 0,
                        "train_session_ids": ["future"],
                        "validation_session_ids": ["past"],
                    }
                ],
            },
        )


def test_write_dataset_handles_late_string_values_after_nulls(tmp_path: Path) -> None:
    rows = [
        _lap("s1", "bahrain", "VER", "HARD", 90_000, season=2024, round_number=1),
        _lap("s2", "jeddah", "LEC", "SOFT", 91_000, season=2024, round_number=2),
    ]
    result = build_temporal_expanding_dataset(rows, block_size=1)
    first_row = dict(result.rows[0])
    second_row = dict(result.rows[1])
    first_row["missing_reason"] = None
    second_row["missing_reason"] = "missing_reference"
    patched = DatasetBuildResult(rows=[*([first_row] * 101), second_row], metadata=result.metadata)

    write_dataset(
        patched,
        dataset_path=tmp_path / "dataset.parquet",
        metadata_path=tmp_path / "dataset.meta.json",
    )

    assert (tmp_path / "dataset.parquet").exists()


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
