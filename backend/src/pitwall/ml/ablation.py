"""Feature ablation helpers for XGBoost temporal diagnostics."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from pitwall.ml.dataset import FEATURE_COLUMNS
from pitwall.ml.train import default_hyperparameters, evaluate_folds

DEFAULT_ABLATION_REPORT_PATH = Path("reports/ml/feature_ablation_report.json")


def ablation_feature_columns() -> dict[str, list[str]]:
    """Return named raw-feature sets used by Day 8.2 ablation diagnostics."""

    full = list(FEATURE_COLUMNS)
    categorical = {"circuit_id", "compound", "driver_code", "team_code", "session_id"}
    return {
        "full": full,
        "no_circuit_one_hot": [feature for feature in full if feature != "circuit_id"],
        "no_reference_lap_time_ms": [
            feature for feature in full if feature != "reference_lap_time_ms"
        ],
        "no_driver_offsets": [
            feature
            for feature in full
            if feature not in {"driver_pace_offset_ms", "driver_pace_offset_missing"}
        ],
        "numeric_only": [feature for feature in full if feature not in categorical],
        "circuit_compound_only": ["circuit_id", "compound"],
    }


def resolve_ablation_feature_columns(feature_set: str) -> list[str]:
    """Resolve a named Day 8.2 feature set for tuning/training."""

    feature_sets = ablation_feature_columns()
    if feature_set not in feature_sets:
        valid = ", ".join(sorted(feature_sets))
        raise ValueError(f"unknown feature set {feature_set!r}; expected one of: {valid}")
    return feature_sets[feature_set]


def run_feature_ablations(
    frame: pl.DataFrame,
    dataset_metadata: Mapping[str, Any],
    *,
    hyperparameters: Mapping[str, Any] | None = None,
    num_boost_round: int = 100,
) -> dict[str, Any]:
    """Evaluate XGBoost over controlled feature groups on the same folds."""

    params = dict(hyperparameters or default_hyperparameters())
    results: list[dict[str, Any]] = []
    for name, columns in ablation_feature_columns().items():
        evaluation = evaluate_folds(
            frame,
            dataset_metadata,
            hyperparameters=params,
            num_boost_round=num_boost_round,
            feature_columns=columns,
        )
        results.append(
            {
                "ablation": name,
                "feature_columns": columns,
                "aggregate_metrics": evaluation.aggregate_metrics,
                "fold_metrics": evaluation.fold_metrics,
            }
        )
    best = min(
        results,
        key=lambda row: float(row["aggregate_metrics"]["holdout_mae_ms"]),
    )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "target_strategy": dataset_metadata.get("target_strategy", "lap_time_delta"),
        "split_strategy": dataset_metadata.get("split_strategy"),
        "num_boost_round": num_boost_round,
        "results": results,
        "best_ablation": {
            "ablation": best["ablation"],
            "holdout_mae_ms": best["aggregate_metrics"]["holdout_mae_ms"],
            "improvement_vs_zero_mae_ms": best["aggregate_metrics"].get(
                "improvement_vs_zero_mae_ms"
            ),
        },
    }


def write_ablation_report(
    report: Mapping[str, Any],
    path: Path = DEFAULT_ABLATION_REPORT_PATH,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
