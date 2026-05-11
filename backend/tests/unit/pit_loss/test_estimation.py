"""Tests for Stream A pit-loss estimation helpers."""

from __future__ import annotations

import pytest

from pitwall.engine.pit_loss import lookup_pit_loss
from pitwall.pit_loss.estimation import (
    GLOBAL_FALLBACK_CIRCUIT_ID,
    PitLossEstimate,
    PitLossSample,
    build_pit_loss_estimates,
    build_pit_loss_report_rows,
    classify_pit_loss_samples,
    compute_sample_statistics,
    pit_loss_table_from_estimates,
    validate_pit_loss_estimates,
)


def test_build_pit_loss_estimates_uses_median_by_circuit_and_team() -> None:
    estimates = build_pit_loss_estimates(
        [
            PitLossSample("monaco", "ferrari", 21_000),
            PitLossSample("monaco", "ferrari", 23_000),
            PitLossSample("monaco", "ferrari", 25_000),
            PitLossSample("monaco", "mclaren", 19_000),
        ]
    )

    by_key = {(row.circuit_id, row.team_code): row for row in estimates}

    assert by_key[("monaco", "ferrari")].pit_loss_ms == 23_000
    assert by_key[("monaco", "ferrari")].n_samples == 3
    assert by_key[("monaco", None)].pit_loss_ms == 22_000
    assert by_key[("monaco", None)].n_samples == 4


def test_runtime_median_is_robust_to_one_extreme_plausible_outlier() -> None:
    estimates = build_pit_loss_estimates(
        [
            PitLossSample("monaco", "ferrari", 21_900),
            PitLossSample("monaco", "ferrari", 22_000),
            PitLossSample("monaco", "ferrari", 22_100),
            PitLossSample("monaco", "ferrari", 39_000),
        ]
    )

    by_key = {(row.circuit_id, row.team_code): row for row in estimates}

    assert by_key[("monaco", "ferrari")].pit_loss_ms == 22_000
    assert by_key[("monaco", "ferrari")].quality == "weak"
    assert by_key[("monaco", "ferrari")].quarantined_samples == 1


def test_trimmed_and_winsorized_means_are_diagnostic_only() -> None:
    stats = compute_sample_statistics(
        [20_000, 20_100, 20_200, 20_300, 20_400, 20_500, 20_600, 39_000]
    )

    assert stats.median_ms == 20_350
    assert stats.trimmed_mean_ms == 20_350
    assert stats.winsorized_mean_ms == 20_350


def test_outlier_classification_marks_impossible_values_as_quarantined() -> None:
    classifications = classify_pit_loss_samples(
        [
            PitLossSample("monaco", "ferrari", 9_000),
            PitLossSample("monaco", "ferrari", 22_000),
            PitLossSample("monaco", "ferrari", 41_000),
        ]
    )

    by_value = {row.sample.pit_loss_ms: row.kind for row in classifications}

    assert by_value[9_000] == "extreme_outlier_quarantined"
    assert by_value[22_000] == "valid_normal"
    assert by_value[41_000] == "extreme_outlier_quarantined"


def test_quality_labels_mark_small_sample_and_high_spread_as_weak() -> None:
    small_sample = build_pit_loss_estimates(
        [
            PitLossSample("monaco", "ferrari", 21_000),
            PitLossSample("monaco", "ferrari", 22_000),
        ]
    )
    high_spread = build_pit_loss_estimates(
        [
            PitLossSample("bahrain", "mclaren", 20_000),
            PitLossSample("bahrain", "mclaren", 21_000),
            PitLossSample("bahrain", "mclaren", 22_000),
            PitLossSample("bahrain", "mclaren", 30_000),
            PitLossSample("bahrain", "mclaren", 31_000),
        ]
    )

    small_by_key = {(row.circuit_id, row.team_code): row for row in small_sample}
    spread_by_key = {(row.circuit_id, row.team_code): row for row in high_spread}

    assert small_by_key[("monaco", "ferrari")].quality == "weak"
    assert spread_by_key[("bahrain", "mclaren")].quality == "weak"


def test_global_fallback_is_conservative_and_lookup_compatible() -> None:
    estimates = build_pit_loss_estimates(
        [
            PitLossSample("monaco", "ferrari", 18_000),
            PitLossSample("monaco", "mclaren", 19_000),
            PitLossSample("bahrain", "ferrari", 20_000),
        ],
        include_global=True,
    )
    table = pit_loss_table_from_estimates(estimates)

    assert table[GLOBAL_FALLBACK_CIRCUIT_ID][None] == 21_000
    assert lookup_pit_loss("unknown", "ferrari", table) == 21_000


def test_report_rows_include_metadata_and_global_fallback() -> None:
    rows = build_pit_loss_report_rows(
        [
            PitLossSample("monaco", "ferrari", 21_000, source="direct_pit_loss_ms"),
            PitLossSample("monaco", "ferrari", 22_000, source="estimated_from_laps"),
            PitLossSample("monaco", "mclaren", 23_000, source="estimated_from_laps"),
        ]
    )

    global_row = next(row for row in rows if row["team_code"] == "GLOBAL_FALLBACK")
    ferrari_row = next(row for row in rows if row["team_code"] == "ferrari")

    assert global_row["aggregation_method"] == "median_conservative_global_v1"
    assert ferrari_row["source"] == "mixed"
    assert ferrari_row["iqr_ms"] == 1_000


def test_pit_loss_table_supports_team_and_circuit_fallback_lookup() -> None:
    table = pit_loss_table_from_estimates(
        [
            PitLossEstimate("monaco", None, 22_000, 4),
            PitLossEstimate("monaco", "ferrari", 23_000, 3),
        ]
    )

    assert lookup_pit_loss("monaco", "ferrari", table) == 23_000
    assert lookup_pit_loss("monaco", "mclaren", table) == 22_000
    assert lookup_pit_loss("spa", "ferrari", table, default=21_000) == 21_000


def test_validate_pit_loss_estimates_rejects_impossible_values() -> None:
    with pytest.raises(ValueError, match="outside realistic range"):
        validate_pit_loss_estimates([PitLossEstimate("monaco", None, 9_000, 2)])

    with pytest.raises(ValueError, match="outside realistic range"):
        validate_pit_loss_estimates([PitLossEstimate("monaco", None, 41_000, 2)])


def test_validate_pit_loss_estimates_requires_circuit_fallback() -> None:
    with pytest.raises(ValueError, match="missing circuit fallback"):
        validate_pit_loss_estimates([PitLossEstimate("monaco", "ferrari", 23_000, 2)])
