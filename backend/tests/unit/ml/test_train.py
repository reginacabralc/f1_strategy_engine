from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import pytest

from pitwall.ml import train
from pitwall.ml.dataset import TARGET_COLUMN

DIAGNOSIS = (
    "functional_training_pipeline; model_quality_depends_on_manifest_coverage_"
    "and_loro_validation"
)


def _metadata_base() -> dict[str, Any]:
    return {
        "target_transform": {"strategy": "identity"},
        "confidence_calibration": {
            "method": "temporal_validation_support_v1",
            "base_confidence": 0.5,
        },
    }


def _frame() -> pl.DataFrame:
    return pl.DataFrame(
        [
            _row("fold_a", "a", "a", "VER", "red_bull_racing", "HARD", 1000.0, "train"),
            _row("fold_a", "b", "b", "LEC", None, "SOFT", -500.0, "holdout"),
            _row("fold_b", "a", "a", "VER", "red_bull_racing", "HARD", 1200.0, "holdout"),
            _row("fold_b", "b", "b", "LEC", "ferrari", "SOFT", -700.0, "train"),
        ]
    )


def _row(
    fold_id: str,
    session_id: str,
    circuit_id: str,
    driver_code: str,
    team_code: str | None,
    compound: str,
    target: float,
    split: str,
) -> dict[str, Any]:
    return {
        "fold_id": fold_id,
        "session_id": session_id,
        "circuit_id": circuit_id,
        "driver_code": driver_code,
        "team_code": team_code,
        "compound": compound,
        "tyre_age": 5,
        "lap_number": 10,
        "stint_number": 1,
        "lap_in_stint": 4,
        "lap_in_stint_ratio": 0.25,
        "race_progress": 0.2,
        "fuel_proxy": 0.8,
        "track_temp_c": 35.0,
        "air_temp_c": 22.0,
        "position": 2,
        "gap_to_ahead_ms": 1200,
        "gap_to_leader_ms": 3000,
        "is_in_traffic": True,
        "dirty_air_proxy_ms": 800,
        "driver_pace_offset_ms": 100.0,
        "driver_pace_offset_missing": False,
        "reference_lap_time_ms": 92_000,
        TARGET_COLUMN: target,
        "row_usable": True,
        "split": split,
    }


class _ZeroModel:
    def __init__(self, train_rows: int) -> None:
        self.train_rows = train_rows

    def predict(self, dmatrix: Any) -> np.ndarray[Any, Any]:
        return np.zeros(dmatrix.num_row())


class _SavableModel(_ZeroModel):
    def save_model(self, path: str) -> None:
        Path(path).write_text("{}")


class _ImportanceModel(_SavableModel):
    def get_score(self, *, importance_type: str) -> dict[str, float]:
        assert importance_type == "gain"
        return {"tyre_age": 4.0, "fuel_proxy": 8.0}


def test_one_hot_encoding_has_stable_feature_columns_and_unknown_category() -> None:
    train_frame = _frame().filter(pl.col("split") == "train")
    holdout_frame = _frame().filter(pl.col("split") == "holdout")

    schema = train.fit_feature_schema(train_frame)
    encoded_train = train.encode_features(train_frame, schema)
    encoded_holdout = train.encode_features(holdout_frame, schema)

    assert encoded_train.feature_names == encoded_holdout.feature_names
    assert "team_code__UNKNOWN" in encoded_train.feature_names
    assert "session_id__a" not in encoded_train.feature_names


def test_missing_categorical_values_encode_as_unknown() -> None:
    frame = _frame().filter(pl.col("session_id") == "b")
    schema = train.fit_feature_schema(frame)
    encoded = train.encode_features(frame, schema)
    unknown_index = encoded.feature_names.index("team_code__UNKNOWN")

    assert encoded.matrix[0, unknown_index] == 1.0


def test_metrics_and_zero_delta_baseline_are_calculated() -> None:
    y_true = np.array([100.0, -100.0, 50.0])
    predictions = np.array([90.0, -70.0, 50.0])

    metrics = train.calculate_metrics(y_true, predictions)
    zero_metrics = train.zero_delta_baseline_metrics(y_true)

    assert metrics.mae_ms == pytest.approx(13.3333333333)
    assert metrics.rmse_ms == pytest.approx(np.sqrt((10.0**2 + 30.0**2) / 3))
    assert metrics.r2 == pytest.approx(0.9538461538)
    assert metrics.median_abs_error_ms == pytest.approx(10.0)
    assert metrics.p75_abs_error_ms == pytest.approx(20.0)
    assert metrics.p90_abs_error_ms == pytest.approx(26.0)
    assert metrics.signed_bias_ms == pytest.approx(6.6666666667)
    assert zero_metrics.mae_ms == pytest.approx(83.3333333333)


def test_target_clip_transform_winsorizes_training_labels_only() -> None:
    target = np.array([-1000.0, 0.0, 100.0, 200.0, 20_000.0])

    fitted = train.fit_target_transform(
        target,
        train.TargetClipConfig(lower_quantile=0.2, upper_quantile=0.8),
    )
    transformed = train.apply_target_transform(target, fitted)

    assert fitted.strategy == "winsorize_quantile"
    assert fitted.lower_bound_ms == pytest.approx(-200.0)
    assert fitted.upper_bound_ms == pytest.approx(4160.0)
    assert transformed.tolist() == pytest.approx([-200.0, 0.0, 100.0, 200.0, 4160.0])


def test_training_metadata_records_confidence_calibration_and_target_transform() -> None:
    fold_result = train.FoldEvaluationResult(
        fold_metrics=[
            {
                "fold_id": "fold_001",
                "holdout_session": "s2",
                "holdout_mae_ms": 900.0,
                "zero_holdout_mae_ms": 1100.0,
                "train_mean_holdout_mae_ms": 950.0,
                "improvement_vs_zero_mae_ms": 200.0,
                "target_distribution": {"count": 2},
            }
        ],
        aggregate_metrics={
            "holdout_mae_ms": 900.0,
            "zero_holdout_mae_ms": 1100.0,
            "train_mean_holdout_mae_ms": 950.0,
            "improvement_vs_zero_mae_ms": 200.0,
            "train_validation_gap_mae_ms": 100.0,
        },
        baseline_metrics={"zero_holdout_mae_ms": 1100.0},
    )

    metadata = train.build_training_metadata(
        dataset_metadata={"sessions_included": ["s1", "s2"], "folds": []},
        dataset_path=Path("data/ml/xgb_pace_dataset.parquet"),
        dataset_metadata_path=Path("data/ml/xgb_pace_dataset.meta.json"),
        final_schema=train.fit_feature_schema(_frame()),
        fold_result=fold_result,
        row_count=4,
        usable_row_count=4,
        hyperparameters=train.default_hyperparameters(),
        num_boost_round=10,
        top_feature_importances=[],
        target_transform=train.FittedTargetTransform(
            strategy="winsorize_quantile",
            lower_bound_ms=-200.0,
            upper_bound_ms=4200.0,
            lower_quantile=0.01,
            upper_quantile=0.99,
            train_rows=4,
        ),
    )

    calibration = metadata["confidence_calibration"]
    assert calibration["method"] == "temporal_validation_support_v1"
    assert calibration["base_confidence"] > 0.5
    assert metadata["target_transform"]["strategy"] == "winsorize_quantile"


def test_train_mean_baseline_predicts_fold_training_mean() -> None:
    train_target = np.array([100.0, 300.0])
    holdout_target = np.array([50.0, 250.0])

    metrics = train.train_mean_baseline_metrics(train_target, holdout_target)

    assert metrics.mae_ms == pytest.approx(100.0)
    assert metrics.rmse_ms == pytest.approx(np.sqrt((150.0**2 + 50.0**2) / 2))


def test_target_distribution_reports_percentiles() -> None:
    values = np.array([-100.0, 0.0, 100.0, 200.0, 300.0])

    distribution = train.target_distribution(values)

    assert distribution["mean_ms"] == pytest.approx(100.0)
    assert distribution["median_ms"] == pytest.approx(100.0)
    assert distribution["std_ms"] == pytest.approx(np.std(values))
    assert distribution["min_ms"] == pytest.approx(-100.0)
    assert distribution["max_ms"] == pytest.approx(300.0)
    assert distribution["p10_ms"] == pytest.approx(-60.0)
    assert distribution["p90_ms"] == pytest.approx(260.0)


def test_signed_bias_by_group_reports_runtime_cohorts() -> None:
    rows = [
        _row("fold_a", "s1", "bahrain", "VER", "red_bull_racing", "HARD", 100.0, "holdout"),
        _row("fold_a", "s1", "bahrain", "LEC", "ferrari", "HARD", 200.0, "holdout"),
        _row("fold_a", "s2", "monaco", "NOR", "mclaren", "SOFT", 300.0, "holdout"),
    ]
    rows[2]["tyre_age"] = 12
    y_true = np.array([100.0, 200.0, 300.0])
    y_pred = np.array([150.0, 100.0, 250.0])

    bias = train.signed_bias_by_group(rows, y_true, y_pred)

    assert bias["circuit_id"][0] == {
        "value": "bahrain",
        "count": 2,
        "signed_bias_ms": pytest.approx(-25.0),
        "mae_ms": pytest.approx(75.0),
    }
    assert bias["compound"][0]["value"] == "HARD"
    assert {row["value"] for row in bias["tyre_age_bucket"]} == {"05-09", "10-14"}
    assert bias["driver_code"][0]["count"] == 1


def test_loro_evaluation_uses_only_fold_train_and_holdout_rows() -> None:
    dataset_metadata = {
        "folds": [
            {
                "fold_id": "fold_a",
                "holdout_session_id": "a",
                "train_session_ids": ["b"],
            },
            {
                "fold_id": "fold_b",
                "holdout_session_id": "b",
                "train_session_ids": ["a"],
            },
        ],
        "sessions_included": ["a", "b"],
    }
    seen_train_rows: list[int] = []

    def fake_trainer(dtrain: Any, _params: dict[str, Any], _rounds: int) -> _ZeroModel:
        seen_train_rows.append(dtrain.num_row())
        return _ZeroModel(dtrain.num_row())

    result = train.evaluate_loro_folds(
        _frame(),
        dataset_metadata,
        hyperparameters=train.default_hyperparameters(),
        num_boost_round=1,
        trainer=fake_trainer,
    )

    assert seen_train_rows == [1, 1]
    assert [metric["holdout_rows"] for metric in result.fold_metrics] == [1, 1]
    assert "train_mae_ms" in result.fold_metrics[0]
    assert "holdout_mae_ms" in result.fold_metrics[0]
    assert "zero_holdout_mae_ms" in result.fold_metrics[0]
    assert "train_mean_holdout_mae_ms" in result.fold_metrics[0]
    assert result.fold_metrics[0]["target_distribution"]["count"] == 1
    assert "signed_bias_by_group" in result.fold_metrics[0]
    assert "signed_bias_by_group" in result.aggregate_metrics
    assert result.aggregate_metrics["holdout_rows"] == 2


def test_temporal_evaluation_uses_validation_split() -> None:
    frame = pl.DataFrame(
        [
            _row("fold_001", "s1", "bahrain", "VER", "red_bull_racing", "HARD", 100.0, "train"),
            _row("fold_001", "s2", "jeddah", "LEC", "ferrari", "HARD", 200.0, "train"),
            _row(
                "fold_001",
                "s3",
                "melbourne",
                "VER",
                "red_bull_racing",
                "HARD",
                300.0,
                "validation",
            ),
        ]
    )
    dataset_metadata = {
        "split_strategy": "temporal_expanding",
        "folds": [
            {
                "fold_id": "fold_001",
                "train_session_ids": ["s1", "s2"],
                "validation_session_ids": ["s3"],
            }
        ],
        "sessions_included": ["s1", "s2", "s3"],
    }
    seen_train_rows: list[int] = []

    def fake_trainer(dtrain: Any, _params: dict[str, Any], _rounds: int) -> _ZeroModel:
        seen_train_rows.append(dtrain.num_row())
        return _ZeroModel(dtrain.num_row())

    result = train.evaluate_folds(
        frame,
        dataset_metadata,
        hyperparameters=train.default_hyperparameters(),
        num_boost_round=1,
        trainer=fake_trainer,
    )

    assert seen_train_rows == [2]
    assert result.fold_metrics[0]["evaluation_split"] == "validation"
    assert result.fold_metrics[0]["evaluation_sessions"] == ["s3"]
    assert result.fold_metrics[0]["validation_mae_ms"] == result.fold_metrics[0]["holdout_mae_ms"]


def test_feature_importance_extracts_sorted_gain_scores() -> None:
    importances = train.extract_feature_importances(
        _ImportanceModel(train_rows=1),
        feature_names=["tyre_age", "fuel_proxy", "missing"],
        max_features=2,
    )

    assert importances == [
        {"feature": "fuel_proxy", "gain": 8.0},
        {"feature": "tyre_age", "gain": 4.0},
    ]


def test_training_metadata_contains_required_keys() -> None:
    fold_result = train.FoldEvaluationResult(
        fold_metrics=[
            {
                "holdout_session": "a",
                "holdout_mae_ms": 1.0,
                "target_distribution": {"count": 1},
            }
        ],
        aggregate_metrics={"holdout_mae_ms": 1.0},
        baseline_metrics={"zero_holdout_mae_ms": 2.0},
    )

    metadata = train.build_training_metadata(
        dataset_metadata={"sessions_included": ["a"], "folds": []},
        dataset_path=Path("data/ml/xgb_pace_dataset.parquet"),
        dataset_metadata_path=Path("data/ml/xgb_pace_dataset.meta.json"),
        final_schema=train.fit_feature_schema(_frame()),
        fold_result=fold_result,
        row_count=4,
        usable_row_count=4,
        hyperparameters=train.default_hyperparameters(),
        num_boost_round=10,
        top_feature_importances=[{"feature": "fuel_proxy", "gain": 8.0}],
    )

    train.validate_model_metadata(metadata)
    assert metadata["target_column"] == TARGET_COLUMN
    assert metadata["model_format"] == "xgboost_native_json"
    assert metadata["scipy_baseline_status"] == "deferred_to_day_9"
    assert metadata["diagnosis"] == DIAGNOSIS
    assert metadata["target_distribution_by_fold"][0]["holdout_session"] == "a"
    assert metadata["top_feature_importances"][0]["feature"] == "fuel_proxy"
    assert metadata["split_strategy"] == "loro"


def test_validation_rejects_pit_loss_feature_leakage() -> None:
    metadata = {
        **_metadata_base(),
        "feature_list": ["tyre_age", "pit_loss_ms"],
        "target_column": TARGET_COLUMN,
        "fold_metrics": [{"holdout_session": "a", "xgb_mae_ms": 1.0}],
        "aggregate_metrics": {"xgb_mae_ms": 1.0},
        "baseline_metrics": {"zero_mae_ms": 2.0},
        "target_distribution_by_fold": [{"holdout_session": "a", "count": 1}],
        "top_feature_importances": [],
        "diagnosis": DIAGNOSIS,
        "hyperparameters": {},
        "training_sessions": ["a"],
        "leakage_policy": [],
    }

    with pytest.raises(ValueError, match="pit-loss"):
        train.validate_model_metadata(metadata)


def test_validation_rejects_missing_fold_metrics() -> None:
    metadata = {
        **_metadata_base(),
        "feature_list": ["tyre_age"],
        "target_column": TARGET_COLUMN,
        "fold_metrics": [],
        "aggregate_metrics": {"xgb_mae_ms": 1.0},
        "baseline_metrics": {"zero_mae_ms": 2.0},
        "target_distribution_by_fold": [],
        "top_feature_importances": [],
        "diagnosis": DIAGNOSIS,
        "hyperparameters": {},
        "training_sessions": ["a"],
        "leakage_policy": [],
    }

    with pytest.raises(ValueError, match="fold_metrics"):
        train.validate_model_metadata(metadata)


def test_save_training_outputs_writes_model_and_metadata(tmp_path: Path) -> None:
    model_path = tmp_path / "models" / "xgb_pace_v1.json"
    metadata_path = tmp_path / "models" / "xgb_pace_v1.meta.json"
    metadata = {
        **_metadata_base(),
        "feature_list": ["tyre_age"],
        "target_column": TARGET_COLUMN,
        "fold_metrics": [{"holdout_session": "a", "xgb_mae_ms": 1.0}],
        "aggregate_metrics": {"xgb_mae_ms": 1.0},
        "baseline_metrics": {"zero_mae_ms": 2.0},
        "target_distribution_by_fold": [{"holdout_session": "a", "count": 1}],
        "top_feature_importances": [],
        "diagnosis": DIAGNOSIS,
        "hyperparameters": {},
        "training_sessions": ["a"],
        "leakage_policy": [],
    }

    train.save_training_outputs(
        model=_SavableModel(train_rows=1),
        model_path=model_path,
        metadata_path=metadata_path,
        metadata=metadata,
    )

    assert model_path.exists()
    assert json.loads(metadata_path.read_text())["feature_list"] == ["tyre_age"]
