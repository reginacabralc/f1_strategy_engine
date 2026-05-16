"""Tests for XGBoostPredictor — loadability, Protocol compliance, runtime features."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
import xgboost as xgb

from pitwall.engine.projection import PaceContext, PacePredictor, UnsupportedContextError
from pitwall.ml.predictor import XGBoostPredictor

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def model_path(tmp_path: Path) -> Path:
    """A real (trivially trained) XGBoost Booster saved as JSON."""
    X = np.array([[1.0], [5.0], [10.0], [15.0], [20.0]])
    y = np.array([74_500.0, 75_000.0, 76_000.0, 77_500.0, 79_500.0])
    dtrain = xgb.DMatrix(X, label=y)
    params = {"max_depth": 1, "eta": 0.3, "objective": "reg:squarederror",
              "verbosity": 0}
    booster = xgb.train(params, dtrain, num_boost_round=2)

    path = tmp_path / "xgb_pace_v1.json"
    booster.save_model(str(path))
    return path


@pytest.fixture()
def predictor(model_path: Path) -> XGBoostPredictor:
    return XGBoostPredictor.from_file(model_path)


# ---------------------------------------------------------------------------
# from_file — loading
# ---------------------------------------------------------------------------


def test_from_file_returns_xgboost_predictor(model_path: Path) -> None:
    p = XGBoostPredictor.from_file(model_path)
    assert isinstance(p, XGBoostPredictor)


def test_from_file_accepts_string_path(model_path: Path) -> None:
    p = XGBoostPredictor.from_file(str(model_path))
    assert isinstance(p, XGBoostPredictor)


def test_from_file_raises_file_not_found_when_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="train-xgb"):
        XGBoostPredictor.from_file(tmp_path / "missing_model.json")


def test_from_file_loads_metadata_sidecar(tmp_path: Path) -> None:
    """When a <model>.meta.json sidecar exists, metadata is populated."""
    X = np.array([[1.0]])
    y = np.array([74_500.0])
    dtrain = xgb.DMatrix(X, label=y)
    booster = xgb.train({"objective": "reg:squarederror", "verbosity": 0},
                        dtrain, num_boost_round=1)

    model_file = tmp_path / "xgb_pace_v1.json"
    booster.save_model(str(model_file))

    meta_file = tmp_path / "xgb_pace_v1.meta.json"
    meta_file.write_text('{"mae_k3_ms": 350, "trained_on": "2024-05-26"}')

    p = XGBoostPredictor.from_file(model_file)
    assert p.metadata["mae_k3_ms"] == 350
    assert p.metadata["trained_on"] == "2024-05-26"


def test_from_file_metadata_is_empty_dict_when_no_sidecar(model_path: Path) -> None:
    p = XGBoostPredictor.from_file(model_path)
    assert isinstance(p.metadata, dict)
    # Fixture has no sidecar file → empty metadata
    assert p.metadata == {}


# ---------------------------------------------------------------------------
# predict — schema-driven runtime feature construction
# ---------------------------------------------------------------------------


def _runtime_metadata() -> dict[str, Any]:
    return {
        "aggregate_metrics": {"holdout_r2": 0.62, "holdout_mae_ms": 950.0},
        "feature_schema": {
            "numeric_features": [
                "tyre_age",
                "lap_number",
                "race_progress",
                "fuel_proxy",
                "gap_to_ahead_ms",
                "driver_pace_offset_ms",
                "driver_pace_offset_missing",
            ],
            "categorical_features": ["circuit_id", "compound", "driver_code", "team_code"],
            "categorical_values": {
                "circuit_id": ["UNKNOWN", "monaco"],
                "compound": ["MEDIUM", "UNKNOWN"],
                "driver_code": ["UNKNOWN", "VER"],
                "team_code": ["UNKNOWN", "red_bull_racing"],
            },
            "feature_names": [
                "tyre_age",
                "lap_number",
                "race_progress",
                "fuel_proxy",
                "gap_to_ahead_ms",
                "driver_pace_offset_ms",
                "driver_pace_offset_missing",
                "circuit_id__UNKNOWN",
                "circuit_id__monaco",
                "compound__MEDIUM",
                "compound__UNKNOWN",
                "driver_code__UNKNOWN",
                "driver_code__VER",
                "team_code__UNKNOWN",
                "team_code__red_bull_racing",
            ],
        },
        "target_column": "lap_time_delta_ms",
        "target_strategy": "session_normalized_delta",
    }


class _CapturingBooster:
    def __init__(self, prediction_delta_ms: float = 1_250.2) -> None:
        self.prediction_delta_ms = prediction_delta_ms
        self.feature_names: list[str] | None = None
        self.values: list[float] | None = None

    def predict(self, matrix: Any) -> np.ndarray[Any, Any]:
        self.feature_names = list(matrix.feature_names or [])
        self.values = matrix.get_data().toarray()[0].tolist()
        return np.array([self.prediction_delta_ms], dtype=float)


def test_predict_encodes_schema_features_and_adds_live_reference() -> None:
    booster = _CapturingBooster(prediction_delta_ms=1_250.2)
    predictor = XGBoostPredictor(booster, _runtime_metadata())
    ctx = PaceContext(
        driver_code="VER",
        circuit_id="monaco",
        compound="MEDIUM",
        tyre_age=7,
        lap_number=20,
        total_laps=78,
        position=2,
        gap_to_ahead_ms=1_200,
        team_code="red_bull_racing",
        reference_lap_time_ms=80_000,
        driver_pace_offset_ms=-125.5,
        driver_pace_offset_missing=False,
    )

    prediction = predictor.predict(ctx)

    assert prediction.predicted_lap_time_ms == 81_250
    assert prediction.confidence == pytest.approx(0.62)
    assert booster.feature_names == _runtime_metadata()["feature_schema"]["feature_names"]
    assert booster.values == pytest.approx(
        [
            7.0,  # tyre_age
            20.0,  # lap_number
            20 / 78,  # race_progress derived from lap/total laps
            1 - (20 / 78),  # fuel_proxy derived from race_progress
            1_200.0,
            -125.5,
            0.0,
            0.0,  # circuit_id__UNKNOWN
            1.0,  # circuit_id__monaco
            1.0,  # compound__MEDIUM
            0.0,  # compound__UNKNOWN
            0.0,  # driver_code__UNKNOWN
            1.0,  # driver_code__VER
            0.0,  # team_code__UNKNOWN
            1.0,  # team_code__red_bull_racing
        ]
    )


def test_predict_maps_unseen_categories_to_unknown_columns() -> None:
    booster = _CapturingBooster(prediction_delta_ms=500.0)
    predictor = XGBoostPredictor(booster, _runtime_metadata())
    ctx = PaceContext(
        driver_code="NOR",
        circuit_id="bahrain",
        compound="HARD",
        tyre_age=5,
        reference_lap_time_ms=75_000,
    )

    predictor.predict(ctx)

    assert booster.values is not None
    feature_values = dict(zip(booster.feature_names or [], booster.values, strict=True))
    assert feature_values["circuit_id__UNKNOWN"] == 1.0
    assert feature_values["compound__UNKNOWN"] == 1.0
    assert feature_values["driver_code__UNKNOWN"] == 1.0
    assert feature_values["team_code__UNKNOWN"] == 1.0


def test_predict_raises_when_live_reference_is_missing() -> None:
    predictor = XGBoostPredictor(_CapturingBooster(), _runtime_metadata())
    ctx = PaceContext(
        driver_code="VER",
        circuit_id="monaco",
        compound="MEDIUM",
        tyre_age=10,
    )

    with pytest.raises(UnsupportedContextError, match="reference_lap_time_ms"):
        predictor.predict(ctx)


def test_predict_raises_when_feature_schema_is_missing(predictor: XGBoostPredictor) -> None:
    ctx = PaceContext(
        driver_code="VER",
        circuit_id="monaco",
        compound="MEDIUM",
        tyre_age=10,
        reference_lap_time_ms=80_000,
    )

    with pytest.raises(UnsupportedContextError, match="feature_schema"):
        predictor.predict(ctx)


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


def test_xgboost_predictor_satisfies_pace_predictor_protocol(
    predictor: XGBoostPredictor,
) -> None:
    """isinstance check against the runtime_checkable PacePredictor Protocol."""
    assert isinstance(predictor, PacePredictor)


def test_xgboost_predictor_class_is_importable_from_ml_module() -> None:
    from pitwall.ml.predictor import XGBoostPredictor as XGB

    assert XGB is XGBoostPredictor
