"""Tests for Phase 3/4 causal dataset construction."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pitwall.causal.dataset_builder import (
    DATASET_VERSION,
    DOWNSTREAM_DECISION_OUTCOME_COLUMNS,
    GAP_SOURCE,
    PACE_SOURCE,
    VIABILITY_FEATURE_COLUMNS,
    build_causal_dataset,
    load_curated_viability_labels_csv,
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
        "recent_pit_stops": 0,
        "projected_pit_exit_gap_to_leader_ms": 12_000,
        "projected_pit_exit_position": 5,
        "traffic_after_pit_cars": 0,
        "nearest_traffic_gap_ms": 4_000,
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


def test_build_causal_dataset_creates_viability_and_evaluation_labels() -> None:
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
    assert row["projected_pit_exit_position"] == 5
    assert row["traffic_after_pit_cars"] == 0
    assert row["traffic_after_pit"] == "low"
    assert row["clean_air_potential"] == "high"
    assert row["pit_lane_congestion"] == "low"
    assert row["pit_window_open"] is True
    assert row["defender_likely_to_cover"] is True
    assert row["safety_car_or_vsc_risk"] is False
    assert row["pace_delta_to_rival_ms"] == 3_000
    assert row["pace_confidence"] == 0.7
    assert row["undercut_viable"] is True
    assert row["undercut_viable_label_source"] == "proxy_modeled_causal_scipy_v1"
    assert row["undercut_success"] is True
    assert row["undercut_success_label_source"] == "auto_derived_pit_cycle_v1"
    assert result.metadata["target_columns"] == ["undercut_viable"]
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


def test_build_causal_dataset_marks_high_pit_exit_traffic() -> None:
    result = build_causal_dataset(
        [
            _pair_row(
                traffic_after_pit_cars=2,
                nearest_traffic_gap_ms=1_000,
            )
        ],
        _degradation_rows(),
        [],
    )

    assert result.rows[0]["traffic_after_pit"] == "high"
    assert result.rows[0]["clean_air_potential"] == "low"


def test_curated_viability_label_can_override_proxy_without_success_leakage() -> None:
    result = build_causal_dataset(
        [_pair_row(gap_to_rival_ms=50_000)],
        _degradation_rows(),
        [
            {
                "session_id": "monaco_2024_R",
                "attacker_code": "ATK",
                "defender_code": "DEF",
                "lap_of_attempt": 10,
                "was_successful": False,
                "notes": "auto_derived_pit_cycle_v1;example",
            }
        ],
        curated_viability_labels=[
            {
                "session_id": "monaco_2024_R",
                "attacker_code": "ATK",
                "defender_code": "DEF",
                "lap_number": 10,
                "undercut_viable": True,
                "label_source": "curated_manual_viability_v1;reviewer=test",
            }
        ],
    )

    row = result.rows[0]
    assert row["undercut_viable"] is True
    assert row["undercut_success"] is False
    assert row["undercut_viable_label_source"].startswith("curated_manual_viability_v1")
    assert result.metadata["curated_viability_rows"] == 1


def test_viability_feature_set_excludes_downstream_columns() -> None:
    assert DOWNSTREAM_DECISION_OUTCOME_COLUMNS.isdisjoint(VIABILITY_FEATURE_COLUMNS)


def test_load_curated_viability_labels_csv(tmp_path: Path) -> None:
    path = tmp_path / "undercut_viability_curated.csv"
    path.write_text(
        "session_id,attacker_code,defender_code,lap_number,undercut_viable,"
        "reviewer,evidence,notes\n"
        "monaco_2024_R,NOR,VER,20,true,rc,video+timing,clear window\n"
    )

    rows = load_curated_viability_labels_csv(path)

    assert rows == [
        {
            "session_id": "monaco_2024_R",
            "attacker_code": "NOR",
            "defender_code": "VER",
            "lap_number": 20,
            "undercut_viable": True,
            "label_source": (
                "curated_manual_viability_v1;reviewer=rc;"
                "evidence=video+timing;notes=clear window"
            ),
        }
    ]
