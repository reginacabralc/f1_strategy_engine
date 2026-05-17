"""Train, evaluate, and validate the Day 8 XGBoost pace model."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import import_module
from inspect import Parameter, signature
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from pitwall.ml.dataset import FEATURE_COLUMNS, TARGET_COLUMN

DEFAULT_DATASET_PATH = Path("data/ml/xgb_pace_dataset.parquet")
DEFAULT_DATASET_METADATA_PATH = Path("data/ml/xgb_pace_dataset.meta.json")
DEFAULT_MODEL_PATH = Path("models/xgb_pace_v1.json")
DEFAULT_MODEL_METADATA_PATH = Path("models/xgb_pace_v1.meta.json")

CATEGORICAL_FEATURES = ("circuit_id", "compound", "driver_code", "team_code")
IDENTIFIER_FEATURES = ("session_id",)
NUMERIC_FEATURES = tuple(
    feature
    for feature in FEATURE_COLUMNS
    if feature not in CATEGORICAL_FEATURES and feature not in IDENTIFIER_FEATURES
)

ModelTrainer = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class FeatureSchema:
    """Concrete encoded feature contract for an XGBoost Booster."""

    numeric_features: tuple[str, ...]
    categorical_features: tuple[str, ...]
    categorical_values: dict[str, tuple[str, ...]]
    feature_names: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "numeric_features": list(self.numeric_features),
            "categorical_features": list(self.categorical_features),
            "categorical_values": {
                feature: list(values)
                for feature, values in self.categorical_values.items()
            },
            "feature_names": list(self.feature_names),
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> FeatureSchema:
        return cls(
            numeric_features=tuple(str(value) for value in payload["numeric_features"]),
            categorical_features=tuple(
                str(value) for value in payload["categorical_features"]
            ),
            categorical_values={
                str(feature): tuple(str(value) for value in values)
                for feature, values in payload["categorical_values"].items()
            },
            feature_names=tuple(str(value) for value in payload["feature_names"]),
        )


@dataclass(frozen=True, slots=True)
class EncodedFeatures:
    matrix: np.ndarray[Any, Any]
    target: np.ndarray[Any, Any] | None
    feature_names: list[str]


@dataclass(frozen=True, slots=True)
class RegressionMetrics:
    mae_ms: float
    rmse_ms: float
    r2: float
    median_abs_error_ms: float
    p75_abs_error_ms: float
    p90_abs_error_ms: float
    signed_bias_ms: float

    def as_dict(self, prefix: str = "") -> dict[str, float]:
        return {
            f"{prefix}mae_ms": self.mae_ms,
            f"{prefix}rmse_ms": self.rmse_ms,
            f"{prefix}r2": self.r2,
            f"{prefix}median_abs_error_ms": self.median_abs_error_ms,
            f"{prefix}p75_abs_error_ms": self.p75_abs_error_ms,
            f"{prefix}p90_abs_error_ms": self.p90_abs_error_ms,
            f"{prefix}signed_bias_ms": self.signed_bias_ms,
        }


@dataclass(frozen=True, slots=True)
class FoldEvaluationResult:
    fold_metrics: list[dict[str, Any]]
    aggregate_metrics: dict[str, Any]
    baseline_metrics: dict[str, Any]


@dataclass(frozen=True, slots=True)
class FinalModelResult:
    model: Any
    schema: FeatureSchema
    train_rows: int
    top_feature_importances: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class TrainingRunResult:
    model_path: Path
    metadata_path: Path
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class TargetClipConfig:
    """Quantile winsorization for robust training labels."""

    lower_quantile: float = 0.01
    upper_quantile: float = 0.99

    def __post_init__(self) -> None:
        if not 0.0 <= self.lower_quantile < self.upper_quantile <= 1.0:
            raise ValueError(
                "target clip quantiles must satisfy "
                "0 <= lower_quantile < upper_quantile <= 1"
            )


@dataclass(frozen=True, slots=True)
class FittedTargetTransform:
    """Fold-local target transform fitted only on training labels."""

    strategy: str
    lower_bound_ms: float | None
    upper_bound_ms: float | None
    lower_quantile: float | None
    upper_quantile: float | None
    train_rows: int

    def to_json(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "lower_bound_ms": self.lower_bound_ms,
            "upper_bound_ms": self.upper_bound_ms,
            "lower_quantile": self.lower_quantile,
            "upper_quantile": self.upper_quantile,
            "train_rows": self.train_rows,
        }


def default_hyperparameters() -> dict[str, Any]:
    """Return the conservative Day 8 XGBoost hyperparameters."""

    return {
        "objective": "reg:squarederror",
        "eval_metric": ["mae", "rmse"],
        "max_depth": 4,
        "eta": 0.08,
        "subsample": 0.9,
        "colsample_bytree": 0.9,
        "seed": 42,
        "verbosity": 0,
    }


def load_dataset(
    dataset_path: Path = DEFAULT_DATASET_PATH,
    metadata_path: Path = DEFAULT_DATASET_METADATA_PATH,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Load Day 7 dataset parquet plus metadata."""

    if not dataset_path.exists():
        raise FileNotFoundError(
            f"XGBoost dataset not found at {dataset_path}. "
            "Run 'make build-xgb-dataset' first."
        )
    if not metadata_path.exists():
        raise FileNotFoundError(
            f"XGBoost dataset metadata not found at {metadata_path}. "
            "Run 'make build-xgb-dataset' first."
        )
    return pl.read_parquet(dataset_path), json.loads(metadata_path.read_text())


def select_usable_rows(frame: pl.DataFrame) -> pl.DataFrame:
    """Keep rows with a valid target and explicit Day 7 usability flag."""

    rows = [
        row
        for row in frame.to_dicts()
        if bool(row.get("row_usable")) and row.get(TARGET_COLUMN) is not None
    ]
    return pl.DataFrame(rows) if rows else pl.DataFrame()


def fit_feature_schema(
    frame: pl.DataFrame,
    *,
    feature_columns: Sequence[str] | None = None,
) -> FeatureSchema:
    """Fit a deterministic one-hot schema from a training frame."""

    raw_features = tuple(feature_columns or FEATURE_COLUMNS)
    columns = set(frame.columns)
    numeric_features = tuple(
        feature
        for feature in raw_features
        if feature in columns
        and feature not in CATEGORICAL_FEATURES
        and feature not in IDENTIFIER_FEATURES
    )
    categorical_features = tuple(
        feature
        for feature in CATEGORICAL_FEATURES
        if feature in columns and feature in raw_features
    )
    rows = frame.to_dicts()
    categorical_values: dict[str, tuple[str, ...]] = {}
    for feature in categorical_features:
        values = {_normalise_category(row.get(feature)) for row in rows}
        values.add("UNKNOWN")
        categorical_values[feature] = tuple(sorted(values))

    feature_names = list(numeric_features)
    for feature in categorical_features:
        feature_names.extend(f"{feature}__{value}" for value in categorical_values[feature])

    return FeatureSchema(
        numeric_features=numeric_features,
        categorical_features=categorical_features,
        categorical_values=categorical_values,
        feature_names=tuple(feature_names),
    )


def encode_features(frame: pl.DataFrame, schema: FeatureSchema) -> EncodedFeatures:
    """Encode rows using an existing feature schema."""

    rows = frame.to_dicts()
    matrix = np.empty((len(rows), len(schema.feature_names)), dtype=np.float32)
    feature_index = {feature: idx for idx, feature in enumerate(schema.feature_names)}

    for row_idx, row in enumerate(rows):
        matrix[row_idx, :] = 0.0
        for feature in schema.numeric_features:
            matrix[row_idx, feature_index[feature]] = _numeric_value(row.get(feature))
        for feature in schema.categorical_features:
            value = _normalise_category(row.get(feature))
            if value not in schema.categorical_values[feature]:
                value = "UNKNOWN"
            encoded_name = f"{feature}__{value}"
            matrix[row_idx, feature_index[encoded_name]] = 1.0

    target: np.ndarray[Any, Any] | None = None
    if TARGET_COLUMN in frame.columns:
        target = np.array([_numeric_value(row.get(TARGET_COLUMN)) for row in rows])
    return EncodedFeatures(matrix=matrix, target=target, feature_names=list(schema.feature_names))


def make_dmatrix(encoded: EncodedFeatures, *, include_target: bool) -> Any:
    """Build a native XGBoost DMatrix from encoded features."""

    xgb = import_module("xgboost")
    label = encoded.target if include_target else None
    return xgb.DMatrix(
        encoded.matrix,
        label=label,
        missing=np.nan,
        feature_names=encoded.feature_names,
    )


def make_dmatrix_with_label(encoded: EncodedFeatures, label: np.ndarray[Any, Any]) -> Any:
    """Build a native XGBoost DMatrix with an explicit label override."""

    xgb = import_module("xgboost")
    return xgb.DMatrix(
        encoded.matrix,
        label=label,
        missing=np.nan,
        feature_names=encoded.feature_names,
    )


def train_booster(
    dtrain: Any,
    hyperparameters: dict[str, Any],
    num_boost_round: int,
    eval_dmatrix: Any | None = None,
) -> Any:
    """Train a native XGBoost Booster."""

    xgb = import_module("xgboost")
    params = dict(hyperparameters)
    early_stopping_rounds = params.pop("early_stopping_rounds", None)
    if early_stopping_rounds is not None and eval_dmatrix is not None:
        return xgb.train(
            params,
            dtrain,
            num_boost_round=num_boost_round,
            evals=[(eval_dmatrix, "validation")],
            early_stopping_rounds=int(early_stopping_rounds),
            verbose_eval=False,
        )
    return xgb.train(params, dtrain, num_boost_round=num_boost_round)


def calculate_metrics(
    y_true: np.ndarray[Any, Any],
    y_pred: np.ndarray[Any, Any],
) -> RegressionMetrics:
    """Compute MAE, RMSE, and R2."""

    if len(y_true) == 0:
        raise ValueError("cannot calculate metrics for zero rows")
    errors = y_pred - y_true
    absolute_errors = np.abs(errors)
    mae = float(np.mean(np.abs(errors)))
    rmse = float(np.sqrt(np.mean(np.square(errors))))
    ss_res = float(np.sum(np.square(errors)))
    ss_tot = float(np.sum(np.square(y_true - np.mean(y_true))))
    r2 = 0.0 if ss_tot == 0.0 else 1.0 - (ss_res / ss_tot)
    return RegressionMetrics(
        mae_ms=mae,
        rmse_ms=rmse,
        r2=float(r2),
        median_abs_error_ms=float(np.median(absolute_errors)),
        p75_abs_error_ms=float(np.percentile(absolute_errors, 75)),
        p90_abs_error_ms=float(np.percentile(absolute_errors, 90)),
        signed_bias_ms=float(np.mean(errors)),
    )


def fit_target_transform(
    target: np.ndarray[Any, Any],
    config: TargetClipConfig | None,
) -> FittedTargetTransform:
    """Fit a leakage-safe target transform from training labels only."""

    if len(target) == 0:
        raise ValueError("cannot fit target transform on zero rows")
    if config is None:
        return FittedTargetTransform(
            strategy="identity",
            lower_bound_ms=None,
            upper_bound_ms=None,
            lower_quantile=None,
            upper_quantile=None,
            train_rows=len(target),
        )
    return FittedTargetTransform(
        strategy="winsorize_quantile",
        lower_bound_ms=float(np.quantile(target, config.lower_quantile)),
        upper_bound_ms=float(np.quantile(target, config.upper_quantile)),
        lower_quantile=config.lower_quantile,
        upper_quantile=config.upper_quantile,
        train_rows=len(target),
    )


def apply_target_transform(
    target: np.ndarray[Any, Any],
    transform: FittedTargetTransform,
) -> np.ndarray[Any, Any]:
    """Apply a fitted target transform without changing evaluation labels."""

    if transform.strategy == "identity":
        return target.astype(np.float64)
    if transform.strategy == "winsorize_quantile":
        if transform.lower_bound_ms is None or transform.upper_bound_ms is None:
            raise ValueError("winsorize_quantile transform requires bounds")
        return np.clip(
            target.astype(np.float64),
            transform.lower_bound_ms,
            transform.upper_bound_ms,
        )
    raise ValueError(f"unsupported target transform strategy: {transform.strategy}")


def zero_delta_baseline_metrics(y_true: np.ndarray[Any, Any]) -> RegressionMetrics:
    """Metrics for the required zero-delta baseline."""

    return calculate_metrics(y_true, np.zeros_like(y_true))


def train_mean_baseline_metrics(
    train_target: np.ndarray[Any, Any],
    holdout_target: np.ndarray[Any, Any],
) -> RegressionMetrics:
    """Metrics for predicting the fold training-target mean on holdout rows."""

    if len(train_target) == 0:
        raise ValueError("cannot calculate train-mean baseline from zero train rows")
    return calculate_metrics(
        holdout_target,
        np.full_like(holdout_target, fill_value=float(np.mean(train_target))),
    )


def target_distribution(target: np.ndarray[Any, Any]) -> dict[str, float | int]:
    """Return target distribution diagnostics for a fold or aggregate."""

    if len(target) == 0:
        raise ValueError("cannot calculate target distribution for zero rows")
    return {
        "count": len(target),
        "mean_ms": float(np.mean(target)),
        "median_ms": float(np.median(target)),
        "std_ms": float(np.std(target)),
        "min_ms": float(np.min(target)),
        "max_ms": float(np.max(target)),
        "p10_ms": float(np.percentile(target, 10)),
        "p90_ms": float(np.percentile(target, 90)),
    }


def signed_bias_by_group(
    rows: Sequence[Mapping[str, Any]],
    y_true: np.ndarray[Any, Any],
    y_pred: np.ndarray[Any, Any],
    *,
    max_groups: int = 20,
) -> dict[str, list[dict[str, Any]]]:
    """Return leakage-safe holdout bias diagnostics for key runtime cohorts."""

    if len(rows) != len(y_true) or len(y_true) != len(y_pred):
        raise ValueError("rows, targets, and predictions must have the same length")
    errors = y_pred - y_true
    absolute_errors = np.abs(errors)
    return {
        "circuit_id": _group_bias(
            rows,
            errors,
            absolute_errors,
            key="circuit_id",
            max_groups=max_groups,
        ),
        "compound": _group_bias(
            rows,
            errors,
            absolute_errors,
            key="compound",
            max_groups=max_groups,
        ),
        "tyre_age_bucket": _group_bias(
            rows,
            errors,
            absolute_errors,
            key="tyre_age",
            bucket_fn=_tyre_age_bucket,
            max_groups=max_groups,
        ),
        "driver_code": _group_bias(
            rows,
            errors,
            absolute_errors,
            key="driver_code",
            max_groups=max_groups,
        ),
        "team_code": _group_bias(
            rows,
            errors,
            absolute_errors,
            key="team_code",
            max_groups=max_groups,
        ),
    }


def evaluate_loro_folds(
    frame: pl.DataFrame,
    dataset_metadata: Mapping[str, Any],
    *,
    hyperparameters: dict[str, Any],
    num_boost_round: int,
    trainer: ModelTrainer = train_booster,
) -> FoldEvaluationResult:
    """Train and evaluate one native Booster per leave-one-race-out fold."""

    return evaluate_folds(
        frame,
        dataset_metadata,
        hyperparameters=hyperparameters,
        num_boost_round=num_boost_round,
        trainer=trainer,
    )


def evaluate_folds(
    frame: pl.DataFrame,
    dataset_metadata: Mapping[str, Any],
    *,
    hyperparameters: dict[str, Any],
    num_boost_round: int,
    trainer: ModelTrainer = train_booster,
    feature_columns: Sequence[str] | None = None,
    target_clip_config: TargetClipConfig | None = None,
) -> FoldEvaluationResult:
    """Train and evaluate one native Booster per dataset fold."""

    usable_frame = select_usable_rows(frame)
    if usable_frame.is_empty():
        raise ValueError("XGBoost training dataset has zero usable rows")

    fold_metrics: list[dict[str, Any]] = []
    all_holdout_targets: list[np.ndarray[Any, Any]] = []
    all_holdout_predictions: list[np.ndarray[Any, Any]] = []
    all_holdout_train_mean_predictions: list[np.ndarray[Any, Any]] = []
    all_holdout_rows: list[dict[str, Any]] = []
    all_train_targets: list[np.ndarray[Any, Any]] = []
    all_train_predictions: list[np.ndarray[Any, Any]] = []

    for fold in dataset_metadata.get("folds", []):
        fold_id = str(fold["fold_id"])
        evaluation_split, evaluation_sessions = _evaluation_split_for_fold(fold)
        holdout_session = ",".join(evaluation_sessions)
        fold_frame = usable_frame.filter(pl.col("fold_id") == fold_id)
        train_frame = fold_frame.filter(pl.col("split") == "train")
        holdout_frame = fold_frame.filter(pl.col("split") == evaluation_split)
        if train_frame.is_empty() or holdout_frame.is_empty():
            raise ValueError(f"fold {fold_id} has empty train or {evaluation_split} split")

        schema = fit_feature_schema(train_frame, feature_columns=feature_columns)
        encoded_train = encode_features(train_frame, schema)
        encoded_holdout = encode_features(holdout_frame, schema)
        train_target = _target_or_raise(encoded_train.target)
        holdout_target = _target_or_raise(encoded_holdout.target)
        target_transform = fit_target_transform(train_target, target_clip_config)
        dtrain = make_dmatrix_with_label(
            encoded_train,
            apply_target_transform(train_target, target_transform),
        )
        dholdout = make_dmatrix(encoded_holdout, include_target=True)
        model = _train_with_optional_validation(
            trainer,
            dtrain,
            hyperparameters,
            num_boost_round,
            eval_dmatrix=dholdout,
        )

        train_predictions = np.asarray(model.predict(dtrain), dtype=np.float64)
        holdout_predictions = np.asarray(model.predict(dholdout), dtype=np.float64)

        train_metrics = calculate_metrics(train_target, train_predictions)
        holdout_metrics = calculate_metrics(holdout_target, holdout_predictions)
        zero_metrics = zero_delta_baseline_metrics(holdout_target)
        train_mean_metrics = train_mean_baseline_metrics(train_target, holdout_target)
        train_mean_predictions = np.full_like(
            holdout_target,
            fill_value=float(np.mean(train_target)),
        )
        holdout_rows = holdout_frame.to_dicts()

        all_train_targets.append(train_target)
        all_train_predictions.append(train_predictions)
        all_holdout_targets.append(holdout_target)
        all_holdout_predictions.append(holdout_predictions)
        all_holdout_train_mean_predictions.append(train_mean_predictions)
        all_holdout_rows.extend(holdout_rows)

        fold_metrics.append(
            {
                "fold_id": fold_id,
                "holdout_session": holdout_session,
                "evaluation_split": evaluation_split,
                "evaluation_sessions": evaluation_sessions,
                "train_rows": train_frame.height,
                "holdout_rows": holdout_frame.height,
                "train_mae_ms": train_metrics.mae_ms,
                "train_rmse_ms": train_metrics.rmse_ms,
                "train_r2": train_metrics.r2,
                "holdout_mae_ms": holdout_metrics.mae_ms,
                "holdout_rmse_ms": holdout_metrics.rmse_ms,
                "holdout_r2": holdout_metrics.r2,
                "zero_holdout_mae_ms": zero_metrics.mae_ms,
                "zero_holdout_rmse_ms": zero_metrics.rmse_ms,
                "zero_holdout_r2": zero_metrics.r2,
                "train_mean_holdout_mae_ms": train_mean_metrics.mae_ms,
                "train_mean_holdout_rmse_ms": train_mean_metrics.rmse_ms,
                "train_mean_holdout_r2": train_mean_metrics.r2,
                "improvement_vs_zero_mae_ms": zero_metrics.mae_ms - holdout_metrics.mae_ms,
                "train_validation_gap_mae_ms": holdout_metrics.mae_ms - train_metrics.mae_ms,
                "validation_mae_ms": holdout_metrics.mae_ms,
                "validation_rmse_ms": holdout_metrics.rmse_ms,
                "validation_r2": holdout_metrics.r2,
                "target_distribution": target_distribution(holdout_target),
                "signed_bias_by_group": signed_bias_by_group(
                    holdout_rows,
                    holdout_target,
                    holdout_predictions,
                ),
                "target_transform": target_transform.to_json(),
                "xgb_train_mae_ms": train_metrics.mae_ms,
                "xgb_train_rmse_ms": train_metrics.rmse_ms,
                "xgb_train_r2": train_metrics.r2,
                "xgb_mae_ms": holdout_metrics.mae_ms,
                "xgb_rmse_ms": holdout_metrics.rmse_ms,
                "xgb_r2": holdout_metrics.r2,
                "zero_mae_ms": zero_metrics.mae_ms,
                "zero_rmse_ms": zero_metrics.rmse_ms,
                "zero_r2": zero_metrics.r2,
                "improvement_mae_ms": zero_metrics.mae_ms - holdout_metrics.mae_ms,
            }
        )

    aggregate = _aggregate_metrics(
        all_train_targets=all_train_targets,
        all_train_predictions=all_train_predictions,
        all_holdout_targets=all_holdout_targets,
        all_holdout_predictions=all_holdout_predictions,
        all_holdout_train_mean_predictions=all_holdout_train_mean_predictions,
        all_holdout_rows=all_holdout_rows,
    )
    baseline_metrics = {
        key: aggregate[key]
        for key in (
            "zero_holdout_mae_ms",
            "zero_holdout_rmse_ms",
            "zero_holdout_r2",
            "train_mean_holdout_mae_ms",
            "train_mean_holdout_rmse_ms",
            "train_mean_holdout_r2",
            "zero_mae_ms",
            "zero_rmse_ms",
            "zero_r2",
        )
    }
    return FoldEvaluationResult(
        fold_metrics=fold_metrics,
        aggregate_metrics=aggregate,
        baseline_metrics=baseline_metrics,
    )


def train_final_model(
    frame: pl.DataFrame,
    *,
    hyperparameters: dict[str, Any],
    num_boost_round: int,
    trainer: ModelTrainer = train_booster,
    feature_columns: Sequence[str] | None = None,
    target_clip_config: TargetClipConfig | None = None,
) -> FinalModelResult:
    """Train the final runtime/demo model on all usable rows."""

    usable_frame = select_usable_rows(frame)
    if usable_frame.is_empty():
        raise ValueError("XGBoost final model has zero usable rows")
    schema = fit_feature_schema(usable_frame, feature_columns=feature_columns)
    encoded = encode_features(usable_frame, schema)
    target = _target_or_raise(encoded.target)
    target_transform = fit_target_transform(target, target_clip_config)
    dtrain = make_dmatrix_with_label(encoded, apply_target_transform(target, target_transform))
    model = _train_with_optional_validation(trainer, dtrain, hyperparameters, num_boost_round)
    return FinalModelResult(
        model=model,
        schema=schema,
        train_rows=usable_frame.height,
        top_feature_importances=extract_feature_importances(
            model,
            feature_names=schema.feature_names,
        ),
    )


def train_xgb_model(
    *,
    dataset_path: Path = DEFAULT_DATASET_PATH,
    dataset_metadata_path: Path = DEFAULT_DATASET_METADATA_PATH,
    model_path: Path = DEFAULT_MODEL_PATH,
    metadata_path: Path = DEFAULT_MODEL_METADATA_PATH,
    hyperparameters: dict[str, Any] | None = None,
    num_boost_round: int = 250,
    feature_columns: Sequence[str] | None = None,
    feature_set_name: str | None = None,
    target_clip_config: TargetClipConfig | None = None,
) -> TrainingRunResult:
    """Run the full Day 8 training flow and write model artifacts."""

    params = hyperparameters or default_hyperparameters()
    frame, dataset_metadata = load_dataset(dataset_path, dataset_metadata_path)
    usable_rows = select_usable_rows(frame).height
    fold_result = evaluate_folds(
        frame,
        dataset_metadata,
        hyperparameters=params,
        num_boost_round=num_boost_round,
        feature_columns=feature_columns,
        target_clip_config=target_clip_config,
    )
    final_result = train_final_model(
        frame,
        hyperparameters=params,
        num_boost_round=num_boost_round,
        feature_columns=feature_columns,
        target_clip_config=target_clip_config,
    )
    final_target = _target_or_raise(
        encode_features(select_usable_rows(frame), final_result.schema).target
    )
    final_target_transform = fit_target_transform(final_target, target_clip_config)
    metadata = build_training_metadata(
        dataset_metadata=dataset_metadata,
        dataset_path=dataset_path,
        dataset_metadata_path=dataset_metadata_path,
        final_schema=final_result.schema,
        fold_result=fold_result,
        row_count=frame.height,
        usable_row_count=usable_rows,
        hyperparameters=params,
        num_boost_round=num_boost_round,
        top_feature_importances=final_result.top_feature_importances,
        raw_feature_columns=tuple(feature_columns or FEATURE_COLUMNS),
        feature_set_name=feature_set_name
        or ("custom" if feature_columns is not None else "full"),
        target_transform=final_target_transform,
    )
    save_training_outputs(
        model=final_result.model,
        model_path=model_path,
        metadata_path=metadata_path,
        metadata=metadata,
    )
    return TrainingRunResult(
        model_path=model_path,
        metadata_path=metadata_path,
        metadata=metadata,
    )


def build_training_metadata(
    *,
    dataset_metadata: Mapping[str, Any],
    dataset_path: Path,
    dataset_metadata_path: Path,
    final_schema: FeatureSchema,
    fold_result: FoldEvaluationResult,
    row_count: int,
    usable_row_count: int,
    hyperparameters: dict[str, Any],
    num_boost_round: int,
    top_feature_importances: Sequence[Mapping[str, Any]],
    raw_feature_columns: Sequence[str] = FEATURE_COLUMNS,
    feature_set_name: str = "full",
    target_transform: FittedTargetTransform | None = None,
) -> dict[str, Any]:
    """Build the model sidecar metadata consumed by validation and reporting."""

    aggregate = dict(fold_result.aggregate_metrics)
    split_strategy = str(dataset_metadata.get("split_strategy", "loro"))
    metadata = {
        "model_type": "xgboost_pace_v1",
        "model_format": "xgboost_native_json",
        "trained_at": datetime.now(UTC).isoformat(),
        "dataset_path": str(dataset_path),
        "dataset_metadata_path": str(dataset_metadata_path),
        "row_count": row_count,
        "usable_row_count": usable_row_count,
        "feature_set": feature_set_name,
        "raw_feature_columns": list(raw_feature_columns),
        "feature_list": list(final_schema.feature_names),
        "feature_schema": final_schema.to_json(),
        "categorical_features": list(final_schema.categorical_features),
        "numeric_features": list(final_schema.numeric_features),
        "target_column": TARGET_COLUMN,
        "target_strategy": dataset_metadata.get("target_strategy", "lap_time_delta"),
        "target_definition": dataset_metadata.get("target_definition"),
        "target_transform": (
            target_transform.to_json()
            if target_transform is not None
            else fit_target_transform(np.array([0.0]), None).to_json()
        ),
        "fold_metrics": fold_result.fold_metrics,
        "target_distribution_by_fold": [
            {
                "fold_id": metric.get("fold_id"),
                "holdout_session": metric.get("holdout_session"),
                **dict(metric.get("target_distribution", {})),
            }
            for metric in fold_result.fold_metrics
        ],
        "aggregate_metrics": aggregate,
        "baseline_metrics": fold_result.baseline_metrics,
        "confidence_calibration": build_confidence_calibration(fold_result),
        "top_feature_importances": [dict(row) for row in top_feature_importances],
        "hyperparameters": hyperparameters,
        "num_boost_round": num_boost_round,
        "training_sessions": list(dataset_metadata.get("sessions_included", [])),
        "split_strategy": split_strategy,
        "session_chronology": list(dataset_metadata.get("session_chronology", [])),
        "final_test_status": dataset_metadata.get("final_test_status", "not_configured"),
        "folds": list(dataset_metadata.get("folds", [])),
        "baseline_reference_source": dataset_metadata.get("baseline_reference_source"),
        "reference_pace_method": dataset_metadata.get("reference_pace_method"),
        "driver_offset_method": dataset_metadata.get("driver_offset_method"),
        "leakage_policy": [
            f"{split_strategy} split by session_id/event_order",
            "fold encoders are fit on training rows only",
            "holdout reference pace comes from Day 7 fold-safe references",
            "holdout driver offsets come from Day 7 fold-safe offsets",
            "pit loss is excluded from lap-level pace modeling",
        ],
        "missing_value_policy": [
            "numeric NaN values are passed to XGBoost",
            "categorical nulls and unseen values encode as UNKNOWN",
        ],
        "scipy_baseline_status": "deferred_to_day_9",
        "overfitting_diagnosis": _diagnose_overfitting(aggregate),
        "diagnosis": (
            "functional_training_pipeline; model_quality_depends_on_manifest_coverage_"
            f"and_{split_strategy}_validation"
        ),
        "known_limitations": [
            "model quality depends on multi-season manifest coverage",
            "with three races, LORO is effectively leave-one-circuit-out",
            "hyperparameter tuning is intentionally small and temporal-CV only",
            "traffic is represented by simple gap proxies",
            "Scipy baseline comparison is deferred to Day 9 backtest work",
        ],
    }
    validate_model_metadata(metadata)
    return metadata


def build_confidence_calibration(fold_result: FoldEvaluationResult) -> dict[str, Any]:
    """Build runtime confidence metadata from temporal validation support."""

    aggregate = fold_result.aggregate_metrics
    holdout_mae = _positive_float(aggregate.get("holdout_mae_ms"))
    zero_mae = _positive_float(aggregate.get("zero_holdout_mae_ms"))
    train_mean_mae = _positive_float(aggregate.get("train_mean_holdout_mae_ms"))
    improvement_vs_zero = float(aggregate.get("improvement_vs_zero_mae_ms", 0.0) or 0.0)
    improvement_vs_train_mean = (
        train_mean_mae - holdout_mae
        if train_mean_mae is not None and holdout_mae is not None
        else 0.0
    )
    zero_ratio = (
        max(0.0, improvement_vs_zero / zero_mae)
        if zero_mae is not None
        else 0.0
    )
    train_mean_ratio = (
        max(0.0, improvement_vs_train_mean / train_mean_mae)
        if train_mean_mae is not None
        else 0.0
    )
    gap = float(aggregate.get("train_validation_gap_mae_ms", 0.0) or 0.0)
    gap_ratio = max(0.0, gap / holdout_mae) if holdout_mae else 1.0
    fold_count = len(fold_result.fold_metrics)
    fold_wins = sum(
        1
        for metric in fold_result.fold_metrics
        if float(metric.get("improvement_vs_zero_mae_ms", 0.0) or 0.0) > 0.0
    )
    fold_win_rate = fold_wins / fold_count if fold_count else 0.0
    zero_scaled = min(1.0, zero_ratio / 0.10)
    train_mean_scaled = min(1.0, train_mean_ratio / 0.03)
    gap_scaled = min(1.0, gap_ratio / 0.50)
    base_confidence = max(
        0.05,
        min(
            0.85,
            0.35
            + 0.15 * fold_win_rate
            + 0.20 * zero_scaled
            + 0.10 * train_mean_scaled
            - 0.15 * gap_scaled,
        ),
    )
    return {
        "method": "temporal_validation_support_v1",
        "base_confidence": base_confidence,
        "fold_count": fold_count,
        "fold_win_rate_vs_zero": fold_win_rate,
        "aggregate_improvement_vs_zero_ratio": zero_ratio,
        "aggregate_improvement_vs_train_mean_ratio": train_mean_ratio,
        "train_validation_gap_ratio": gap_ratio,
        "notes": (
            "Calibrates runtime confidence from temporal validation support, "
            "not raw aggregate R2."
        ),
    }


def save_training_outputs(
    *,
    model: Any,
    model_path: Path,
    metadata_path: Path,
    metadata: Mapping[str, Any],
) -> None:
    """Persist native Booster JSON and sidecar metadata."""

    validate_model_metadata(metadata)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(str(model_path))
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")


def validate_model_metadata(metadata: Mapping[str, Any]) -> None:
    """Validate model sidecar metadata without loading artifacts."""

    required_keys = [
        "feature_list",
        "target_column",
        "target_transform",
        "fold_metrics",
        "target_distribution_by_fold",
        "aggregate_metrics",
        "baseline_metrics",
        "confidence_calibration",
        "top_feature_importances",
        "diagnosis",
        "hyperparameters",
        "training_sessions",
        "leakage_policy",
    ]
    missing = [key for key in required_keys if key not in metadata]
    if missing:
        raise ValueError(f"missing XGBoost model metadata key(s): {missing}")
    if metadata.get("target_column") != TARGET_COLUMN:
        raise ValueError(f"unexpected target column: {metadata.get('target_column')}")

    features = [str(feature) for feature in metadata.get("feature_list", [])]
    raw_features = [str(feature) for feature in metadata.get("raw_feature_columns", [])]
    leaked = sorted(feature for feature in [*features, *raw_features] if "pit_loss" in feature)
    if leaked:
        raise ValueError(f"pit-loss features are not allowed in pace model: {leaked}")

    fold_metrics = metadata.get("fold_metrics", [])
    if not isinstance(fold_metrics, list) or not fold_metrics:
        raise ValueError("fold_metrics must contain at least one leave-one-race-out result")
    target_distributions = metadata.get("target_distribution_by_fold", [])
    if not isinstance(target_distributions, list) or not target_distributions:
        raise ValueError("target_distribution_by_fold must contain holdout diagnostics")
    for metric in fold_metrics:
        _validate_metric_values(metric)
    _validate_metric_values(metadata.get("aggregate_metrics", {}))
    _validate_metric_values(metadata.get("baseline_metrics", {}))


def validate_model_artifacts(
    *,
    model_path: Path = DEFAULT_MODEL_PATH,
    metadata_path: Path = DEFAULT_MODEL_METADATA_PATH,
    dataset_path: Path = DEFAULT_DATASET_PATH,
    dataset_metadata_path: Path = DEFAULT_DATASET_METADATA_PATH,
    sample_size: int = 16,
) -> dict[str, Any]:
    """Validate saved model artifacts and predict on a small dataset sample."""

    if not model_path.exists():
        raise FileNotFoundError(f"XGBoost model file not found: {model_path}")
    if not metadata_path.exists():
        raise FileNotFoundError(f"XGBoost model metadata not found: {metadata_path}")

    metadata = json.loads(metadata_path.read_text())
    validate_model_metadata(metadata)

    frame, dataset_metadata = load_dataset(dataset_path, dataset_metadata_path)
    expected_sessions = set(dataset_metadata.get("sessions_included", []))
    split_strategy = str(dataset_metadata.get("split_strategy") or "loro")
    evaluation_sessions = {
        str(session)
        for metric in metadata["fold_metrics"]
        for session in metric.get("evaluation_sessions", [metric.get("holdout_session")])
        if session
    }
    if split_strategy == "loro":
        missing_sessions = sorted(expected_sessions - evaluation_sessions)
        if missing_sessions:
            raise ValueError(f"fold metrics missing holdout session(s): {missing_sessions}")

    xgb = import_module("xgboost")
    booster = xgb.Booster()
    booster.load_model(str(model_path))

    from pitwall.ml.predictor import XGBoostPredictor

    XGBoostPredictor.from_file(model_path)

    schema = FeatureSchema.from_json(metadata["feature_schema"])
    sample = select_usable_rows(frame).head(sample_size)
    if sample.is_empty():
        raise ValueError("cannot validate model predictions with zero usable dataset rows")
    encoded = encode_features(sample, schema)
    dmatrix = make_dmatrix(encoded, include_target=False)
    predictions = np.asarray(booster.predict(dmatrix), dtype=np.float64)
    if not np.all(np.isfinite(predictions)):
        raise ValueError("XGBoost model produced non-finite predictions")

    return {
        "model_path": str(model_path),
        "metadata_path": str(metadata_path),
        "row_count": metadata["row_count"],
        "usable_row_count": metadata["usable_row_count"],
        "feature_count": len(metadata["feature_list"]),
        "fold_count": len(metadata["fold_metrics"]),
        "sessions": sorted(expected_sessions),
        "aggregate_metrics": metadata["aggregate_metrics"],
        "baseline_metrics": metadata["baseline_metrics"],
        "top_feature_importances": metadata["top_feature_importances"],
        "diagnosis": metadata["diagnosis"],
        "prediction_sample_size": len(predictions),
    }


def format_fold_metrics(fold_metrics: Sequence[Mapping[str, Any]]) -> str:
    """Return a concise fold metrics table for scripts/docs."""

    header = (
        "holdout_session     train_rows  holdout_rows  "
        "train_mae  train_rmse  train_r2  holdout_mae  holdout_rmse  "
        "holdout_r2  zero_mae  mean_mae  improvement"
    )
    lines = [header]
    for metric in fold_metrics:
        lines.append(
            f"{metric['holdout_session']:<18} "
            f"{int(metric['train_rows']):>10} "
            f"{int(metric['holdout_rows']):>13} "
            f"{float(metric['train_mae_ms']):>10.1f} "
            f"{float(metric['train_rmse_ms']):>11.1f} "
            f"{float(metric['train_r2']):>8.3f} "
            f"{float(metric['holdout_mae_ms']):>12.1f} "
            f"{float(metric['holdout_rmse_ms']):>13.1f} "
            f"{float(metric['holdout_r2']):>10.3f} "
            f"{float(metric['zero_holdout_mae_ms']):>9.1f} "
            f"{float(metric['train_mean_holdout_mae_ms']):>8.1f} "
            f"{float(metric['improvement_vs_zero_mae_ms']):>11.1f}"
        )
    return "\n".join(lines)


def format_target_distributions(fold_metrics: Sequence[Mapping[str, Any]]) -> str:
    """Return a concise target distribution table for holdout folds."""

    header = (
        "holdout_session     count  mean_ms  median_ms  std_ms  "
        "min_ms  p10_ms  p90_ms  max_ms"
    )
    lines = [header]
    for metric in fold_metrics:
        distribution = metric["target_distribution"]
        lines.append(
            f"{metric['holdout_session']:<18} "
            f"{int(distribution['count']):>5} "
            f"{float(distribution['mean_ms']):>8.1f} "
            f"{float(distribution['median_ms']):>10.1f} "
            f"{float(distribution['std_ms']):>7.1f} "
            f"{float(distribution['min_ms']):>7.1f} "
            f"{float(distribution['p10_ms']):>7.1f} "
            f"{float(distribution['p90_ms']):>7.1f} "
            f"{float(distribution['max_ms']):>7.1f}"
        )
    return "\n".join(lines)


def format_feature_importances(importances: Sequence[Mapping[str, Any]]) -> str:
    """Return a concise feature importance table."""

    if not importances:
        return "feature                 gain\n(no gain importances reported)"
    lines = ["feature                 gain"]
    for row in importances:
        lines.append(f"{row['feature']!s:<22} {float(row['gain']):.4f}")
    return "\n".join(lines)


def extract_feature_importances(
    model: Any,
    *,
    feature_names: Sequence[str],
    max_features: int = 15,
) -> list[dict[str, Any]]:
    """Extract sorted feature-gain importances from a trained Booster if available."""

    get_score = getattr(model, "get_score", None)
    if get_score is None:
        return []
    scores = get_score(importance_type="gain")
    allowed_features = set(feature_names)
    rows: list[dict[str, Any]] = [
        {"feature": str(feature), "gain": float(gain)}
        for feature, gain in scores.items()
        if str(feature) in allowed_features
    ]
    return sorted(rows, key=lambda row: float(row["gain"]), reverse=True)[:max_features]


def _aggregate_metrics(
    *,
    all_train_targets: Sequence[np.ndarray[Any, Any]],
    all_train_predictions: Sequence[np.ndarray[Any, Any]],
    all_holdout_targets: Sequence[np.ndarray[Any, Any]],
    all_holdout_predictions: Sequence[np.ndarray[Any, Any]],
    all_holdout_train_mean_predictions: Sequence[np.ndarray[Any, Any]],
    all_holdout_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    train_target = np.concatenate(all_train_targets)
    train_predictions = np.concatenate(all_train_predictions)
    holdout_target = np.concatenate(all_holdout_targets)
    holdout_predictions = np.concatenate(all_holdout_predictions)
    holdout_train_mean_predictions = np.concatenate(all_holdout_train_mean_predictions)

    train_metrics = calculate_metrics(train_target, train_predictions)
    holdout_metrics = calculate_metrics(holdout_target, holdout_predictions)
    zero_metrics = zero_delta_baseline_metrics(holdout_target)
    train_mean_metrics = calculate_metrics(holdout_target, holdout_train_mean_predictions)
    return {
        "train_rows": len(train_target),
        "holdout_rows": len(holdout_target),
        "train_mae_ms": train_metrics.mae_ms,
        "train_rmse_ms": train_metrics.rmse_ms,
        "train_r2": train_metrics.r2,
        "holdout_mae_ms": holdout_metrics.mae_ms,
        "holdout_rmse_ms": holdout_metrics.rmse_ms,
        "holdout_r2": holdout_metrics.r2,
        "zero_holdout_mae_ms": zero_metrics.mae_ms,
        "zero_holdout_rmse_ms": zero_metrics.rmse_ms,
        "zero_holdout_r2": zero_metrics.r2,
        "train_mean_holdout_mae_ms": train_mean_metrics.mae_ms,
        "train_mean_holdout_rmse_ms": train_mean_metrics.rmse_ms,
        "train_mean_holdout_r2": train_mean_metrics.r2,
        "improvement_vs_zero_mae_ms": zero_metrics.mae_ms - holdout_metrics.mae_ms,
        "train_validation_gap_mae_ms": holdout_metrics.mae_ms - train_metrics.mae_ms,
        "target_distribution": target_distribution(holdout_target),
        "signed_bias_by_group": signed_bias_by_group(
            all_holdout_rows,
            holdout_target,
            holdout_predictions,
        ),
        "xgb_train_mae_ms": train_metrics.mae_ms,
        "xgb_train_rmse_ms": train_metrics.rmse_ms,
        "xgb_train_r2": train_metrics.r2,
        "xgb_mae_ms": holdout_metrics.mae_ms,
        "xgb_rmse_ms": holdout_metrics.rmse_ms,
        "xgb_r2": holdout_metrics.r2,
        "zero_mae_ms": zero_metrics.mae_ms,
        "zero_rmse_ms": zero_metrics.rmse_ms,
        "zero_r2": zero_metrics.r2,
        "improvement_mae_ms": zero_metrics.mae_ms - holdout_metrics.mae_ms,
    }


def _evaluation_split_for_fold(fold: Mapping[str, Any]) -> tuple[str, list[str]]:
    validation_sessions = [str(value) for value in fold.get("validation_session_ids", [])]
    if validation_sessions:
        return "validation", validation_sessions
    holdout_session = fold.get("holdout_session_id")
    if holdout_session:
        return "holdout", [str(holdout_session)]
    test_sessions = [str(value) for value in fold.get("test_session_ids", [])]
    if test_sessions:
        return "test", test_sessions
    raise ValueError(f"fold has no evaluation sessions: {fold}")


def _train_with_optional_validation(
    trainer: ModelTrainer,
    dtrain: Any,
    hyperparameters: dict[str, Any],
    num_boost_round: int,
    *,
    eval_dmatrix: Any | None = None,
) -> Any:
    trainer_signature = signature(trainer)
    accepts_varargs = any(
        parameter.kind == Parameter.VAR_POSITIONAL
        for parameter in trainer_signature.parameters.values()
    )
    accepts_eval = accepts_varargs or len(trainer_signature.parameters) >= 4
    if accepts_eval:
        return trainer(dtrain, hyperparameters, num_boost_round, eval_dmatrix)
    return trainer(dtrain, hyperparameters, num_boost_round)


def _positive_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) and numeric > 0.0 else None


def _group_bias(
    rows: Sequence[Mapping[str, Any]],
    errors: np.ndarray[Any, Any],
    absolute_errors: np.ndarray[Any, Any],
    *,
    key: str,
    bucket_fn: Callable[[Any], str] | None = None,
    max_groups: int,
) -> list[dict[str, Any]]:
    groups: dict[str, list[int]] = {}
    for idx, row in enumerate(rows):
        raw_value = row.get(key)
        group = bucket_fn(raw_value) if bucket_fn is not None else _normalise_category(raw_value)
        groups.setdefault(group, []).append(idx)

    diagnostics: list[dict[str, Any]] = []
    for group, indices in groups.items():
        group_errors = errors[indices]
        group_absolute_errors = absolute_errors[indices]
        diagnostics.append(
            {
                "value": group,
                "count": len(indices),
                "signed_bias_ms": float(np.mean(group_errors)),
                "mae_ms": float(np.mean(group_absolute_errors)),
            }
        )
    return sorted(
        diagnostics,
        key=lambda row: (-int(row["count"]), str(row["value"])),
    )[:max_groups]


def _tyre_age_bucket(value: Any) -> str:
    tyre_age = _numeric_value(value)
    if math.isnan(tyre_age):
        return "UNKNOWN"
    if tyre_age < 5:
        return "00-04"
    if tyre_age < 10:
        return "05-09"
    if tyre_age < 15:
        return "10-14"
    if tyre_age < 20:
        return "15-19"
    if tyre_age < 25:
        return "20-24"
    return "25+"


def _diagnose_overfitting(aggregate: Mapping[str, Any]) -> str:
    xgb_mae = float(aggregate.get("xgb_mae_ms", math.inf))
    train_mae = float(aggregate.get("xgb_train_mae_ms", math.inf))
    zero_mae = float(aggregate.get("zero_mae_ms", math.inf))
    if xgb_mae >= zero_mae:
        return "xgb_does_not_beat_zero_delta_baseline"
    if train_mae > 0 and xgb_mae > train_mae * 1.5:
        return "holdout_error_much_higher_than_train_error"
    return "no_strong_overfitting_signal"


def _normalise_category(value: Any) -> str:
    if value is None:
        return "UNKNOWN"
    text = str(value).strip()
    return text if text else "UNKNOWN"


def _numeric_value(value: Any) -> float:
    if value is None:
        return np.nan
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return np.nan
    return numeric if math.isfinite(numeric) else np.nan


def _target_or_raise(target: np.ndarray[Any, Any] | None) -> np.ndarray[Any, Any]:
    if target is None:
        raise ValueError(f"encoded frame is missing target column {TARGET_COLUMN}")
    if np.isnan(target).any():
        raise ValueError("encoded target contains NaN")
    return target.astype(np.float64)


def _validate_metric_values(metric: Any) -> None:
    if not isinstance(metric, Mapping):
        raise ValueError(f"metric payload must be a mapping: {metric!r}")
    for key, value in metric.items():
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, int | float) and not math.isfinite(float(value)):
            raise ValueError(f"non-finite metric value for {key}: {value}")
