"""Leakage-safe baseline ladder for temporal pace-model evaluation."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
import polars as pl

from pitwall.ingest.normalize import to_float
from pitwall.ml.dataset import TARGET_COLUMN
from pitwall.ml.train import calculate_metrics, select_usable_rows

DEFAULT_BASELINE_REPORT_PATH = Path("reports/ml/baseline_ladder.json")


@dataclass(frozen=True, slots=True)
class BaselinePrediction:
    name: str
    predictions: np.ndarray[Any, Any]
    notes: str


def evaluate_baseline_ladder(
    frame: pl.DataFrame,
    dataset_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate simple baselines using each fold's training rows only."""

    usable = select_usable_rows(frame)
    fold_metrics: list[dict[str, Any]] = []
    aggregate_targets: dict[str, list[np.ndarray[Any, Any]]] = defaultdict(list)
    aggregate_predictions: dict[str, list[np.ndarray[Any, Any]]] = defaultdict(list)
    baseline_notes: dict[str, str] = {}

    for fold in dataset_metadata.get("folds", []):
        fold_id = str(fold["fold_id"])
        evaluation_split = _evaluation_split(fold)
        fold_frame = usable.filter(pl.col("fold_id") == fold_id)
        train_rows = fold_frame.filter(pl.col("split") == "train").to_dicts()
        eval_rows = fold_frame.filter(pl.col("split") == evaluation_split).to_dicts()
        if not train_rows or not eval_rows:
            continue
        target = np.array([float(row[TARGET_COLUMN]) for row in eval_rows], dtype=np.float64)
        for prediction in _predict_baselines(train_rows, eval_rows):
            metrics = calculate_metrics(target, prediction.predictions)
            fold_metrics.append(
                {
                    "fold_id": fold_id,
                    "baseline": prediction.name,
                    "evaluation_split": evaluation_split,
                    "rows": len(eval_rows),
                    "mae_ms": metrics.mae_ms,
                    "rmse_ms": metrics.rmse_ms,
                    "r2": metrics.r2,
                    "notes": prediction.notes,
                }
            )
            aggregate_targets[prediction.name].append(target)
            aggregate_predictions[prediction.name].append(prediction.predictions)
            baseline_notes[prediction.name] = prediction.notes

    aggregate_metrics: list[dict[str, Any]] = []
    for name in sorted(aggregate_predictions):
        target = np.concatenate(aggregate_targets[name])
        predictions = np.concatenate(aggregate_predictions[name])
        metrics = calculate_metrics(target, predictions)
        aggregate_metrics.append(
            {
                "baseline": name,
                "rows": len(target),
                "mae_ms": metrics.mae_ms,
                "rmse_ms": metrics.rmse_ms,
                "r2": metrics.r2,
                "notes": baseline_notes[name],
            }
        )
    best = (
        min(aggregate_metrics, key=lambda row: float(row["mae_ms"]))
        if aggregate_metrics
        else None
    )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "split_strategy": dataset_metadata.get("split_strategy"),
        "target_strategy": dataset_metadata.get("target_strategy", "lap_time_delta"),
        "fold_metrics": fold_metrics,
        "aggregate_metrics": aggregate_metrics,
        "best_baseline": best,
        "deferred_baselines": {
            "ridge_elasticnet_numeric": (
                "scikit-learn is not a current project dependency; defer until target/reference "
                "stability is proven or add an ADR for the dependency"
            )
        },
    }


def write_baseline_report(
    report: Mapping[str, Any],
    path: Path = DEFAULT_BASELINE_REPORT_PATH,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


def _predict_baselines(
    train_rows: Sequence[Mapping[str, Any]],
    eval_rows: Sequence[Mapping[str, Any]],
) -> list[BaselinePrediction]:
    train_targets = [float(row[TARGET_COLUMN]) for row in train_rows]
    train_mean = float(np.mean(train_targets))
    return [
        BaselinePrediction(
            name="zero_delta",
            predictions=np.zeros(len(eval_rows), dtype=np.float64),
            notes="predicts zero target delta",
        ),
        BaselinePrediction(
            name="train_mean",
            predictions=np.full(len(eval_rows), train_mean, dtype=np.float64),
            notes="predicts fold training-target mean",
        ),
        BaselinePrediction(
            name="circuit_compound_median",
            predictions=_median_predictions(
                train_rows,
                eval_rows,
                group_keys=("circuit_id", "compound"),
                fallback=train_mean,
            ),
            notes="median target by circuit+compound from fold training rows",
        ),
        BaselinePrediction(
            name="circuit_compound_tyre_age_curve",
            predictions=_tyre_age_curve_predictions(train_rows, eval_rows, fallback=train_mean),
            notes="quadratic target curve by circuit+compound+tyre_age from fold training rows",
        ),
        BaselinePrediction(
            name="driver_team_adjusted_median",
            predictions=_driver_team_adjusted_predictions(
                train_rows,
                eval_rows,
                fallback=train_mean,
            ),
            notes=(
                "circuit+compound median plus driver/team residual medians "
                "from fold training rows"
            ),
        ),
    ]


def _median_predictions(
    train_rows: Sequence[Mapping[str, Any]],
    eval_rows: Sequence[Mapping[str, Any]],
    *,
    group_keys: tuple[str, ...],
    fallback: float,
) -> np.ndarray[Any, Any]:
    values: dict[tuple[str, ...], list[float]] = defaultdict(list)
    for row in train_rows:
        values[_key(row, group_keys)].append(float(row[TARGET_COLUMN]))
    medians = {key: float(median(rows)) for key, rows in values.items()}
    return np.array([medians.get(_key(row, group_keys), fallback) for row in eval_rows])


def _tyre_age_curve_predictions(
    train_rows: Sequence[Mapping[str, Any]],
    eval_rows: Sequence[Mapping[str, Any]],
    *,
    fallback: float,
) -> np.ndarray[Any, Any]:
    grouped: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    for row in train_rows:
        tyre_age = to_float(row.get("tyre_age"))
        target = to_float(row.get(TARGET_COLUMN))
        if tyre_age is None or target is None:
            continue
        grouped[(str(row.get("circuit_id") or ""), str(row.get("compound") or ""))].append(
            (tyre_age, target)
        )
    curves: dict[tuple[str, str], tuple[float, ...]] = {}
    medians: dict[tuple[str, str], float] = {}
    for key, pairs in grouped.items():
        targets = [target for _age, target in pairs]
        medians[key] = float(median(targets))
        if len(pairs) >= 3:
            ages = np.array([age for age, _target in pairs], dtype=np.float64)
            y = np.array(targets, dtype=np.float64)
            degree = 2 if len(set(ages)) >= 3 else 1
            curves[key] = tuple(float(value) for value in np.polyfit(ages, y, degree))
    predictions: list[float] = []
    for row in eval_rows:
        key = (str(row.get("circuit_id") or ""), str(row.get("compound") or ""))
        tyre_age = to_float(row.get("tyre_age"))
        if key in curves and tyre_age is not None:
            predictions.append(float(np.polyval(curves[key], tyre_age)))
        else:
            predictions.append(medians.get(key, fallback))
    return np.array(predictions, dtype=np.float64)


def _driver_team_adjusted_predictions(
    train_rows: Sequence[Mapping[str, Any]],
    eval_rows: Sequence[Mapping[str, Any]],
    *,
    fallback: float,
) -> np.ndarray[Any, Any]:
    group_values: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in train_rows:
        group_values[(str(row.get("circuit_id") or ""), str(row.get("compound") or ""))].append(
            float(row[TARGET_COLUMN])
        )
    group_medians = {key: float(median(values)) for key, values in group_values.items()}
    driver_residuals: dict[tuple[str, str], list[float]] = defaultdict(list)
    team_residuals: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in train_rows:
        group_key = (str(row.get("circuit_id") or ""), str(row.get("compound") or ""))
        base = group_medians.get(group_key, fallback)
        residual = float(row[TARGET_COLUMN]) - base
        compound = str(row.get("compound") or "")
        driver_residuals[(str(row.get("driver_code") or ""), compound)].append(residual)
        team_residuals[(str(row.get("team_code") or ""), compound)].append(residual)
    driver_medians = {key: float(median(values)) for key, values in driver_residuals.items()}
    team_medians = {key: float(median(values)) for key, values in team_residuals.items()}
    predictions: list[float] = []
    for row in eval_rows:
        compound = str(row.get("compound") or "")
        group_key = (str(row.get("circuit_id") or ""), compound)
        base = group_medians.get(group_key, fallback)
        adjustment = driver_medians.get(
            (str(row.get("driver_code") or ""), compound),
            team_medians.get((str(row.get("team_code") or ""), compound), 0.0),
        )
        predictions.append(base + adjustment)
    return np.array(predictions, dtype=np.float64)


def _evaluation_split(fold: Mapping[str, Any]) -> str:
    if fold.get("validation_session_ids"):
        return "validation"
    if fold.get("test_session_ids"):
        return "test"
    return "holdout"


def _key(row: Mapping[str, Any], group_keys: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(str(row.get(key) or "") for key in group_keys)
