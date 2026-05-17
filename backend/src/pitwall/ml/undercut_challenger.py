"""Offline pair-level undercut challenger models.

This module intentionally does not plug into the live undercut engine.  It
compares pair-level classifiers against the existing structural labels so the
repo can decide, with evidence, whether a decision-layer model is mature enough
to promote later.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from pitwall.ml.train import EncodedFeatures, FeatureSchema, encode_features

DEFAULT_PAIR_DATASET_PATH = Path("data/causal/undercut_driver_rival_lap.parquet")
DEFAULT_CHALLENGER_REPORT_PATH = Path("reports/ml/undercut_challenger_report.json")

PAIR_NUMERIC_FEATURES = (
    "lap_number",
    "total_laps",
    "laps_remaining",
    "current_position",
    "rival_position",
    "gap_to_rival_ms",
    "attacker_gap_to_leader_ms",
    "defender_gap_to_leader_ms",
    "attacker_tyre_age",
    "defender_tyre_age",
    "tyre_age_delta",
    "attacker_laps_in_stint",
    "defender_laps_in_stint",
    "track_temp_c",
    "air_temp_c",
    "pit_loss_estimate_ms",
    "projected_pit_exit_position",
    "traffic_after_pit_cars",
    "nearest_traffic_gap_ms",
    "fresh_tyre_advantage_ms",
    "projected_gain_if_pit_now_ms",
    "required_gain_to_clear_rival_ms",
    "projected_gap_after_pit_ms",
    "pace_confidence",
)
PAIR_CATEGORICAL_FEATURES = (
    "circuit_id",
    "race_phase",
    "attacker_compound",
    "defender_compound",
    "attacker_next_compound",
    "traffic_after_pit",
    "clean_air_potential",
)
PAIR_FEATURE_COLUMNS = (*PAIR_NUMERIC_FEATURES, *PAIR_CATEGORICAL_FEATURES)


@dataclass(frozen=True, slots=True)
class PairTemporalSplit:
    train: pl.DataFrame
    validation: pl.DataFrame
    train_sessions: tuple[str, ...]
    validation_sessions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PairLevelMetrics:
    rows: int
    positive_rate: float
    precision: float
    recall: float
    f1: float
    brier_score: float
    pr_auc: float | None

    def to_json(self) -> dict[str, Any]:
        return {
            "rows": self.rows,
            "positive_rate": self.positive_rate,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "brier_score": self.brier_score,
            "pr_auc": self.pr_auc,
        }


def load_pair_dataset(path: Path = DEFAULT_PAIR_DATASET_PATH) -> pl.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"pair-level undercut dataset not found at {path}; "
            "run `make build-causal-dataset` first"
        )
    return pl.read_parquet(path)


def build_temporal_session_split(
    frame: pl.DataFrame,
    *,
    validation_fraction: float = 0.30,
) -> PairTemporalSplit:
    """Split pair rows by session so validation never shares a race with train."""

    if not 0.0 < validation_fraction < 1.0:
        raise ValueError("validation_fraction must be in (0, 1)")
    usable = frame.filter(pl.col("row_usable") == True)  # noqa: E712
    sessions = (
        usable.select(["season", "session_id"])
        .unique()
        .sort(["season", "session_id"])
        .to_dicts()
    )
    if len(sessions) < 2:
        raise ValueError("pair-level challenger requires at least two sessions")
    validation_count = max(1, round(len(sessions) * validation_fraction))
    split_index = max(1, len(sessions) - validation_count)
    train_sessions = tuple(str(row["session_id"]) for row in sessions[:split_index])
    validation_sessions = tuple(str(row["session_id"]) for row in sessions[split_index:])
    return PairTemporalSplit(
        train=usable.filter(pl.col("session_id").is_in(train_sessions)),
        validation=usable.filter(pl.col("session_id").is_in(validation_sessions)),
        train_sessions=train_sessions,
        validation_sessions=validation_sessions,
    )


def classification_metrics(
    *,
    y_true: Sequence[bool],
    probabilities: Sequence[float],
    threshold: float = 0.5,
) -> PairLevelMetrics:
    target = np.array([bool(value) for value in y_true], dtype=bool)
    probs = np.array([float(value) for value in probabilities], dtype=np.float64)
    if len(target) == 0 or len(probs) != len(target):
        raise ValueError("classification metrics require aligned non-empty arrays")
    predictions = probs >= threshold
    true_positive = int(np.sum(predictions & target))
    false_positive = int(np.sum(predictions & ~target))
    false_negative = int(np.sum(~predictions & target))
    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive or false_positive
        else 0.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive or false_negative
        else 0.0
    )
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    brier = float(np.mean(np.square(probs - target.astype(np.float64))))
    return PairLevelMetrics(
        rows=len(target),
        positive_rate=float(np.mean(target.astype(np.float64))),
        precision=precision,
        recall=recall,
        f1=f1,
        brier_score=brier,
        pr_auc=_average_precision(target, probs),
    )


def evaluate_pair_level_challengers(
    frame: pl.DataFrame,
    *,
    validation_fraction: float = 0.30,
    random_seed: int = 42,
) -> dict[str, Any]:
    """Train and evaluate offline pair-level challengers."""

    split = build_temporal_session_split(frame, validation_fraction=validation_fraction)
    train = _with_proxy_label(split.train)
    validation = _with_proxy_label(split.validation)
    schema = _fit_pair_schema(train)
    encoded_train = _encode_pair_features(train, schema)
    encoded_validation = _encode_pair_features(validation, schema)
    y_train = _label_array(train, "proxy_label")
    y_validation = _label_array(validation, "proxy_label")

    xgb_probabilities = _fit_xgb_classifier(
        encoded_train,
        y_train,
        encoded_validation,
        random_seed=random_seed,
    )
    results: dict[str, Any] = {
        "model_family": "pair_level_undercut_challenger_v1",
        "status": "offline_challenger_only",
        "label_warning": (
            "proxy_label is undercut_viable from structural/scipy labels; "
            "observed_success is reported separately and is too sparse for runtime promotion."
        ),
        "train_sessions": list(split.train_sessions),
        "validation_sessions": list(split.validation_sessions),
        "features": list(PAIR_FEATURE_COLUMNS),
        "xgboost_proxy_metrics": classification_metrics(
            y_true=[bool(value) for value in y_validation.tolist()],
            probabilities=[float(value) for value in xgb_probabilities.tolist()],
        ).to_json(),
        "xgboost_observed_success_metrics": _observed_success_metrics(
            validation,
            xgb_probabilities,
        ),
        "random_forest_proxy_metrics": _random_forest_metrics(
            encoded_train,
            y_train,
            encoded_validation,
            y_validation,
            random_seed=random_seed,
        ),
    }
    results["selected_runtime_action"] = "do_not_promote_pair_model_to_runtime"
    return results


def write_challenger_report(
    report: Mapping[str, Any],
    path: Path = DEFAULT_CHALLENGER_REPORT_PATH,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


def _fit_pair_schema(frame: pl.DataFrame) -> FeatureSchema:
    rows = frame.to_dicts()
    categorical_values: dict[str, tuple[str, ...]] = {}
    for feature in PAIR_CATEGORICAL_FEATURES:
        values = {
            str(row.get(feature) or "UNKNOWN").strip() or "UNKNOWN"
            for row in rows
        }
        values.add("UNKNOWN")
        categorical_values[feature] = tuple(sorted(values))

    feature_names = list(PAIR_NUMERIC_FEATURES)
    for feature in PAIR_CATEGORICAL_FEATURES:
        feature_names.extend(f"{feature}__{value}" for value in categorical_values[feature])
    return FeatureSchema(
        numeric_features=PAIR_NUMERIC_FEATURES,
        categorical_features=PAIR_CATEGORICAL_FEATURES,
        categorical_values=categorical_values,
        feature_names=tuple(feature_names),
    )


def _encode_pair_features(frame: pl.DataFrame, schema: FeatureSchema) -> EncodedFeatures:
    return encode_features(frame.select([*PAIR_FEATURE_COLUMNS, "proxy_label"]), schema)


def _with_proxy_label(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.with_columns(pl.col("undercut_viable").cast(pl.Int8).alias("proxy_label"))


def _label_array(frame: pl.DataFrame, column: str) -> np.ndarray[Any, Any]:
    return np.array([bool(value) for value in frame[column].to_list()], dtype=bool)


def _fit_xgb_classifier(
    train: EncodedFeatures,
    y_train: np.ndarray[Any, Any],
    validation: EncodedFeatures,
    *,
    random_seed: int,
) -> np.ndarray[Any, Any]:
    xgb = import_module("xgboost")
    dtrain = xgb.DMatrix(
        train.matrix,
        label=y_train.astype(np.float64),
        missing=np.nan,
        feature_names=train.feature_names,
    )
    dvalidation = xgb.DMatrix(
        validation.matrix,
        missing=np.nan,
        feature_names=validation.feature_names,
    )
    positives = max(1, int(np.sum(y_train)))
    negatives = max(1, len(y_train) - positives)
    booster = xgb.train(
        {
            "objective": "binary:logistic",
            "eval_metric": "logloss",
            "max_depth": 3,
            "eta": 0.05,
            "min_child_weight": 10,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "lambda": 20,
            "alpha": 5,
            "scale_pos_weight": negatives / positives,
            "tree_method": "hist",
            "seed": random_seed,
            "verbosity": 0,
        },
        dtrain,
        num_boost_round=200,
    )
    return np.asarray(booster.predict(dvalidation), dtype=np.float64)


def _random_forest_metrics(
    train: EncodedFeatures,
    y_train: np.ndarray[Any, Any],
    validation: EncodedFeatures,
    y_validation: np.ndarray[Any, Any],
    *,
    random_seed: int,
) -> dict[str, Any]:
    try:
        ensemble = import_module("sklearn.ensemble")
    except ImportError:
        return {
            "status": "skipped",
            "reason": "scikit-learn is not a direct project dependency",
        }
    classifier = ensemble.RandomForestClassifier(
        n_estimators=200,
        max_depth=8,
        min_samples_leaf=20,
        class_weight="balanced",
        random_state=random_seed,
        n_jobs=1,
    )
    matrix = np.nan_to_num(train.matrix, nan=0.0)
    validation_matrix = np.nan_to_num(validation.matrix, nan=0.0)
    classifier.fit(matrix, y_train)
    probabilities = classifier.predict_proba(validation_matrix)[:, 1]
    metrics = classification_metrics(
        y_true=[bool(value) for value in y_validation.tolist()],
        probabilities=[float(value) for value in probabilities.tolist()],
    ).to_json()
    return {"status": "evaluated_optional_dependency", **metrics}


def _observed_success_metrics(
    validation: pl.DataFrame,
    probabilities: np.ndarray[Any, Any],
) -> dict[str, Any]:
    rows = validation.with_row_index("_row_index").filter(pl.col("undercut_success").is_not_null())
    if rows.is_empty():
        return {
            "status": "skipped_no_observed_success_labels",
            "rows": 0,
        }
    indices = [int(value) for value in rows["_row_index"].to_list()]
    return {
        "status": "evaluated_sparse_observed_labels",
        **classification_metrics(
            y_true=[bool(value) for value in rows["undercut_success"].to_list()],
            probabilities=[float(probabilities[index]) for index in indices],
        ).to_json(),
    }


def _average_precision(
    y_true: np.ndarray[Any, Any],
    probabilities: np.ndarray[Any, Any],
) -> float | None:
    if len(set(bool(value) for value in y_true)) < 2:
        return None
    try:
        metrics = import_module("sklearn.metrics")
    except ImportError:
        return None
    return float(metrics.average_precision_score(y_true, probabilities))
