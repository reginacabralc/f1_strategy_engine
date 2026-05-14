"""Tests for Phase 3/4 causal dataset construction."""

from __future__ import annotations

from datetime import UTC, datetime

from pitwall.causal.dataset_builder import (
    DATASET_VERSION,
    GAP_SOURCE,
    PACE_SOURCE,
    build_causal_dataset,
    validate_causal_dataset_rows,
)


def _pair_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "session_id": "monaco_2024_R",
        "circuit_id": "monaco",
        "season": 2024,
        "lap_number": 10,
        "total_laps": 78,
        "attacker_code": "ATK",
        "defender_code": "DEF",
        "attacker_team_code": "ferrari",
        "defender_team_code": "mclaren",
        "current_position": 2,
        "rival_position": 1,
        "gap_to_rival_ms": 2_000,
        "current_gap_to_car_ahead_ms": 2_000,
        "attacker_gap_to_leader_ms": 2_000,
        "defender_gap_to_leader_ms": 0,
        "attacker_lap_time_ms": 82_000,
        "defender_lap_time_ms": 83_000,
        "attacker_compound": "MEDIUM",
        "defender_compound": "MEDIUM",
        "attacker_tyre_age": 15,
        "defender_tyre_age": 30,
        "attacker_stint_number": 1,
        "defender_stint_number": 1,
        "attacker_laps_in_stint": 15,
        "defender_laps_in_stint": 30,
        "track_status": "GREEN",
        "track_temp_c": 42.0,
        "air_temp_c": 26.0,
        "rainfall": False,
        "pit_now": True,
        "pit_loss_estimate_ms": 10_000,
    }
    row.update(overrides)
    return row


def _degradation_rows() -> list[dict[str, object]]:
    return [
        {
            "circuit_id": "monaco",
            "compound": "MEDIUM",
            "a": 80_000,
            "b": 200,
            "c": 0,
            "r_squared": 0.8,
        },
        {
            "circuit_id": "monaco",
            "compound": "HARD",
            "a": 78_000,
            "b": 20,
            "c": 0,
            "r_squared": 0.7,
        },
    ]


def test_build_causal_dataset_creates_viability_and_success_labels() -> None:
    result = build_causal_dataset(
        [_pair_row()],
        _degradation_rows(),
        [
            {
                "session_id": "monaco_2024_R",
                "attacker_code": "ATK",
                "defender_code": "DEF",
                "lap_of_attempt": 10,
                "was_successful": True,
                "notes": "auto_derived_pit_cycle_v1;example",
            }
        ],
        generated_at=datetime(2026, 5, 14, tzinfo=UTC),
    )

    assert len(result.rows) == 1
    row = result.rows[0]
    assert row["gap_source"] == GAP_SOURCE
    assert row["pace_source"] == PACE_SOURCE
    assert row["label_version"] == DATASET_VERSION
    assert row["undercut_viable"] is True
    assert row["undercut_viable_label_source"] == "observed_auto_derived_pit_cycle_v1"
    assert row["undercut_success"] is True
    assert row["undercut_success_label_source"] == "auto_derived_pit_cycle_v1"
    assert result.metadata["observed_success_rows"] == 1
    validate_causal_dataset_rows(result.rows, result.metadata)


def test_build_causal_dataset_marks_unusable_rows_with_reason() -> None:
    result = build_causal_dataset(
        [_pair_row(gap_to_rival_ms=None)],
        _degradation_rows(),
        [],
    )

    assert result.rows[0]["row_usable"] is False
    assert result.rows[0]["undercut_viable"] is None
    assert result.rows[0]["missing_reason"] == "missing_gap_to_rival"
