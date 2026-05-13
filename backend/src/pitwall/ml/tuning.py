"""Small temporal-CV hyperparameter search for XGBoost pace models."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from pitwall.ml.train import (
    FoldEvaluationResult,
    ModelTrainer,
    default_hyperparameters,
    evaluate_folds,
    train_booster,
)

DEFAULT_TUNING_REPORT_PATH = Path("data/ml/xgb_tuning_report.json")


@dataclass(frozen=True, slots=True)
class CandidateResult:
    candidate_id: str
    hyperparameters: dict[str, Any]
    num_boost_round: int
    aggregate_metrics: Mapping[str, Any]
    fold_metrics: Sequence[Mapping[str, Any]]
    feature_columns: tuple[str, ...] | None = None

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "hyperparameters": self.hyperparameters,
            "num_boost_round": self.num_boost_round,
            "feature_columns": (
                list(self.feature_columns) if self.feature_columns is not None else None
            ),
            "aggregate_metrics": dict(self.aggregate_metrics),
            "fold_metrics": [dict(row) for row in self.fold_metrics],
        }


@dataclass(frozen=True, slots=True)
class TuningResult:
    candidates: tuple[CandidateResult, ...]
    selected_candidate: CandidateResult
    selection_criterion: str
    generated_at: str

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "selection_criterion": self.selection_criterion,
            "selected_config": self.selected_candidate.to_json_dict(),
            "candidates": [candidate.to_json_dict() for candidate in self.candidates],
        }

    def write_json(self, path: Path = DEFAULT_TUNING_REPORT_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_json_dict(), indent=2, sort_keys=True) + "\n")


def candidate_hyperparameters() -> list[dict[str, Any]]:
    """Return a curated small search list; intentionally not a Cartesian grid."""

    base = default_hyperparameters()
    candidates = [
        _candidate(3, 0.03, 0.95, 0.95, 1, 1),
        _candidate(3, 0.06, 0.9, 0.9, 5, 1),
        _candidate(4, 0.06, 0.9, 0.9, 1, 1),
        _candidate(4, 0.08, 0.8, 0.95, 5, 5),
        _candidate(5, 0.03, 0.95, 0.8, 1, 5),
        _candidate(5, 0.06, 0.8, 0.8, 5, 5),
        _candidate(3, 0.1, 0.8, 0.95, 5, 5),
        _candidate(4, 0.1, 0.95, 0.8, 1, 1),
        _candidate(2, 0.02, 0.8, 0.8, 20, 20, alpha=5),
        _candidate(1, 0.06, 0.9, 0.9, 20, 20, alpha=10),
        _candidate(3, 0.03, 0.7, 0.7, 30, 30, alpha=10),
        _candidate(2, 0.1, 0.7, 0.7, 50, 50, alpha=20),
    ]
    return [{**base, **candidate} for candidate in candidates]


def _candidate(
    max_depth: int,
    eta: float,
    subsample: float,
    colsample_bytree: float,
    min_child_weight: int,
    regularization: int,
    *,
    alpha: int | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "max_depth": max_depth,
        "eta": eta,
        "subsample": subsample,
        "colsample_bytree": colsample_bytree,
        "min_child_weight": min_child_weight,
        "lambda": regularization,
    }
    if alpha is not None:
        params["alpha"] = alpha
    return params


def tune_xgb_hyperparameters(
    frame: pl.DataFrame,
    dataset_metadata: Mapping[str, Any],
    *,
    candidates: Sequence[Mapping[str, Any]] | None = None,
    num_boost_round: int = 200,
    trainer: ModelTrainer = train_booster,
    feature_columns: Sequence[str] | None = None,
) -> TuningResult:
    """Evaluate candidate configs on dataset folds and select the best one."""

    candidate_rows: list[CandidateResult] = []
    selected_features = tuple(feature_columns) if feature_columns is not None else None
    for index, params in enumerate(candidates or candidate_hyperparameters(), start=1):
        evaluation: FoldEvaluationResult = evaluate_folds(
            frame,
            dataset_metadata,
            hyperparameters=dict(params),
            num_boost_round=num_boost_round,
            trainer=trainer,
            feature_columns=feature_columns,
        )
        candidate_rows.append(
            CandidateResult(
                candidate_id=f"candidate_{index:02d}",
                hyperparameters=dict(params),
                num_boost_round=num_boost_round,
                aggregate_metrics=evaluation.aggregate_metrics,
                fold_metrics=evaluation.fold_metrics,
                feature_columns=selected_features,
            )
        )
    selected = select_best_candidate(candidate_rows)
    return TuningResult(
        candidates=tuple(candidate_rows),
        selected_candidate=selected,
        selection_criterion="min validation MAE, then RMSE, then train-validation MAE gap",
        generated_at=datetime.now(UTC).isoformat(),
    )


def select_best_candidate(candidates: Sequence[CandidateResult]) -> CandidateResult:
    if not candidates:
        raise ValueError("cannot select from zero tuning candidates")
    return min(
        candidates,
        key=lambda candidate: (
            float(candidate.aggregate_metrics.get("holdout_mae_ms", float("inf"))),
            float(candidate.aggregate_metrics.get("holdout_rmse_ms", float("inf"))),
            float(candidate.aggregate_metrics.get("train_validation_gap_mae_ms", float("inf"))),
        ),
    )


def load_selected_hyperparameters(path: Path = DEFAULT_TUNING_REPORT_PATH) -> dict[str, Any] | None:
    selected = load_selected_tuning_config(path)
    return selected[0] if selected else None


def load_selected_tuning_config(
    path: Path = DEFAULT_TUNING_REPORT_PATH,
) -> tuple[dict[str, Any], int] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    selected = payload.get("selected_config", {})
    params = selected.get("hyperparameters")
    if not isinstance(params, Mapping):
        return None
    return dict(params), int(selected.get("num_boost_round", 250))
