"""Tests for XGBoostPredictor — loadability, Protocol compliance, error paths."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from pitwall.engine.projection import PaceContext, PacePredictor, UnsupportedContextError
from pitwall.ml.predictor import XGBoostPredictor
from pitwall.ml.train import FeatureSchema

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def model_path(tmp_path: Path) -> Path:
    """A real (trivially trained) XGBoost Booster saved as JSON."""
    xgb = pytest.importorskip("xgboost", exc_type=ImportError)
    X = np.array([[1.0], [5.0], [10.0], [15.0], [20.0]])
    y = np.array([74_500.0, 75_000.0, 76_000.0, 77_500.0, 79_500.0])
    dtrain = xgb.DMatrix(X, label=y)
    params = {
        "max_depth": 1,
        "eta": 0.3,
        "objective": "reg:squarederror",
        "verbosity": 0,
    }
    booster = xgb.train(params, dtrain, num_boost_round=2)

    path = tmp_path / "xgb_pace_v1.json"
    booster.save_model(str(path))
    return path


@pytest.fixture()
def predictor(model_path: Path) -> XGBoostPredictor:
    return XGBoostPredictor.from_file(model_path)


@pytest.fixture()
def runtime_predictor() -> XGBoostPredictor:
    schema = FeatureSchema(
        numeric_features=("tyre_age", "reference_lap_time_ms", "driver_pace_offset_ms"),
        categorical_features=("circuit_id", "compound", "driver_code", "team_code"),
        categorical_values={
            "circuit_id": ("UNKNOWN", "monaco"),
            "compound": ("MEDIUM", "UNKNOWN"),
            "driver_code": ("UNKNOWN", "VER"),
            "team_code": ("UNKNOWN", "red_bull"),
        },
        feature_names=(
            "tyre_age",
            "reference_lap_time_ms",
            "driver_pace_offset_ms",
            "circuit_id__UNKNOWN",
            "circuit_id__monaco",
            "compound__MEDIUM",
            "compound__UNKNOWN",
            "driver_code__UNKNOWN",
            "driver_code__VER",
            "team_code__UNKNOWN",
            "team_code__red_bull",
        ),
    )
    return XGBoostPredictor(
        _FakeBooster(delta_ms=750.0),
        {
            "feature_schema": schema.to_json(),
            "aggregate_metrics": {"holdout_r2": 0.42},
            "runtime_reference_pace": {
                "by_circuit_compound": {"monaco|MEDIUM": 80_000},
                "by_compound": {"MEDIUM": 80_500},
            },
            "runtime_driver_offsets": {
                "exact": {"VER|monaco|MEDIUM": -100},
                "by_driver_compound": {"VER|MEDIUM": -50},
            },
        },
    )


class _FakeBooster:
    def __init__(self, *, delta_ms: float) -> None:
        self.delta_ms = delta_ms
        self.last_feature_names: list[str] | None = None

    def predict(self, dmatrix: Any) -> np.ndarray[Any, Any]:
        self.last_feature_names = list(dmatrix.feature_names)
        return np.array([self.delta_ms], dtype=float)


class _FakeDMatrix:
    def __init__(self, feature_names: list[str]) -> None:
        self.feature_names = feature_names


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
    xgb = pytest.importorskip("xgboost", exc_type=ImportError)
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
# predict — raises UnsupportedContextError (feature pipeline not wired yet)
# ---------------------------------------------------------------------------


def test_predict_raises_unsupported_context_error(predictor: XGBoostPredictor) -> None:
    ctx = PaceContext(
        driver_code="VER",
        circuit_id="monaco",
        compound="MEDIUM",
        tyre_age=10,
    )
    with pytest.raises(UnsupportedContextError, match="feature_schema"):
        predictor.predict(ctx)


def test_predict_error_message_includes_circuit_and_compound(
    predictor: XGBoostPredictor,
) -> None:
    ctx = PaceContext(
        driver_code="NOR",
        circuit_id="bahrain",
        compound="HARD",
        tyre_age=5,
    )
    with pytest.raises(UnsupportedContextError) as exc_info:
        predictor.predict(ctx)
    assert "feature_schema" in str(exc_info.value)


def test_predict_uses_runtime_feature_pipeline(
    runtime_predictor: XGBoostPredictor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_make_dmatrix(encoded: Any, *, include_target: bool) -> _FakeDMatrix:
        assert include_target is False
        return _FakeDMatrix(encoded.feature_names)

    monkeypatch.setattr("pitwall.ml.predictor.make_dmatrix", _fake_make_dmatrix)

    prediction = runtime_predictor.predict(
        PaceContext(
            driver_code="VER",
            team_code="red_bull",
            circuit_id="monaco",
            compound="MEDIUM",
            tyre_age=10,
            total_laps=78,
            laps_remaining=50,
        )
    )

    assert prediction.predicted_lap_time_ms > 80_000
    assert prediction.confidence == 0.42


def test_is_available_reflects_runtime_reference_metadata(
    runtime_predictor: XGBoostPredictor,
) -> None:
    assert runtime_predictor.is_available("monaco", "MEDIUM") is True
    assert runtime_predictor.is_available("monaco", "INTER") is False
    assert runtime_predictor.is_available("unknown", "MEDIUM") is True


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
