"""Tests for XGBoostPredictor — loadability, Protocol compliance, error paths."""

from __future__ import annotations

from pathlib import Path

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
# predict — raises UnsupportedContextError (feature pipeline not wired yet)
# ---------------------------------------------------------------------------


def test_predict_raises_unsupported_context_error(predictor: XGBoostPredictor) -> None:
    ctx = PaceContext(
        driver_code="VER",
        circuit_id="monaco",
        compound="MEDIUM",
        tyre_age=10,
    )
    with pytest.raises(UnsupportedContextError, match="feature pipeline"):
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
    assert "bahrain" in str(exc_info.value)
    assert "HARD" in str(exc_info.value)


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
