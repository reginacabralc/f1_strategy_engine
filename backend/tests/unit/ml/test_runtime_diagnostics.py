"""Tests for runtime XGBoost feature parity diagnostics."""

from __future__ import annotations

from typing import Any

from pitwall.engine.projection import PaceContext
from pitwall.ml.predictor import XGBoostPredictor
from pitwall.ml.runtime_diagnostics import diagnose_xgboost_runtime_features


class _NoopBooster:
    def predict(self, matrix: Any) -> list[float]:
        return [0.0]


def _metadata() -> dict[str, Any]:
    return {
        "target_column": "lap_time_delta_ms",
        "target_strategy": "session_normalized_delta",
        "feature_schema": {
            "numeric_features": [
                "tyre_age",
                "lap_number",
                "lap_in_stint_ratio",
                "race_progress",
                "driver_pace_offset_ms",
                "driver_pace_offset_missing",
            ],
            "categorical_features": ["circuit_id", "compound", "driver_code", "team_code"],
            "categorical_values": {
                "circuit_id": ["UNKNOWN", "monaco"],
                "compound": ["UNKNOWN", "MEDIUM"],
                "driver_code": ["UNKNOWN", "VER"],
                "team_code": ["UNKNOWN", "red_bull_racing"],
            },
            "feature_names": [
                "tyre_age",
                "lap_number",
                "lap_in_stint_ratio",
                "race_progress",
                "driver_pace_offset_ms",
                "driver_pace_offset_missing",
                "circuit_id__UNKNOWN",
                "circuit_id__monaco",
                "compound__UNKNOWN",
                "compound__MEDIUM",
                "driver_code__UNKNOWN",
                "driver_code__VER",
                "team_code__UNKNOWN",
                "team_code__red_bull_racing",
            ],
        },
    }


def test_runtime_diagnostics_report_delta_reference_but_no_reference_feature() -> None:
    predictor = XGBoostPredictor(_NoopBooster(), _metadata())
    report = diagnose_xgboost_runtime_features(
        predictor,
        PaceContext(
            driver_code="VER",
            circuit_id="monaco",
            compound="MEDIUM",
            tyre_age=7,
            lap_number=20,
            total_laps=78,
            team_code="red_bull_racing",
            reference_lap_time_ms=80_000,
            driver_pace_offset_missing=True,
        ),
    )

    assert report.predicts_delta is True
    assert report.requires_reference_for_prediction is True
    assert report.reference_lap_time_feature_present is False
    assert "reference_lap_time_ms" not in report.feature_names


def test_runtime_diagnostics_expose_missing_and_unknown_features() -> None:
    predictor = XGBoostPredictor(_NoopBooster(), _metadata())
    report = diagnose_xgboost_runtime_features(
        predictor,
        PaceContext(
            driver_code="PIA",
            circuit_id="silverstone",
            compound="HARD",
            tyre_age=7,
            lap_number=20,
            total_laps=78,
            reference_lap_time_ms=80_000,
            driver_pace_offset_missing=True,
        ),
    )

    assert "lap_in_stint_ratio" in report.missing_numeric_features
    assert report.unknown_categorical_features == {
        "circuit_id": "silverstone",
        "compound": "HARD",
        "driver_code": "PIA",
        "team_code": "unknown",
    }
    assert report.driver_pace_offset_missing is True
