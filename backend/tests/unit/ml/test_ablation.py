from __future__ import annotations

from pitwall.ml.ablation import ablation_feature_columns


def test_ablation_feature_sets_remove_requested_groups() -> None:
    feature_sets = ablation_feature_columns()

    assert "circuit_id" not in feature_sets["no_circuit_one_hot"]
    assert "reference_lap_time_ms" not in feature_sets["no_reference_lap_time_ms"]
    assert "driver_pace_offset_ms" not in feature_sets["no_driver_offsets"]
    assert "driver_pace_offset_missing" not in feature_sets["no_driver_offsets"]
    assert "circuit_id" not in feature_sets["numeric_only"]
    assert "compound" not in feature_sets["numeric_only"]
    assert feature_sets["circuit_compound_only"] == ["circuit_id", "compound"]

