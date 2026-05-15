#!/usr/bin/env python
"""Tune XGBoost hyperparameters on temporal validation folds."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from pitwall.ml.ablation import resolve_ablation_feature_columns
from pitwall.ml.train import DEFAULT_DATASET_METADATA_PATH, DEFAULT_DATASET_PATH, load_dataset
from pitwall.ml.tuning import DEFAULT_TUNING_REPORT_PATH, tune_xgb_hyperparameters


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--dataset-meta", type=Path, default=DEFAULT_DATASET_METADATA_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_TUNING_REPORT_PATH)
    parser.add_argument("--rounds", type=int, default=200)
    parser.add_argument("--feature-set", default=os.getenv("FEATURE_SET", "full"))
    args = parser.parse_args()

    frame, metadata = load_dataset(args.dataset, args.dataset_meta)
    feature_columns = resolve_ablation_feature_columns(args.feature_set)
    result = tune_xgb_hyperparameters(
        frame,
        metadata,
        num_boost_round=args.rounds,
        feature_columns=feature_columns,
    )
    result.write_json(args.report)

    selected = result.selected_candidate
    aggregate = selected.aggregate_metrics
    print(f"Wrote {args.report}")
    print(f"selected: {selected.candidate_id}")
    print(f"criterion: {result.selection_criterion}")
    print(f"holdout_mae_ms: {float(aggregate['holdout_mae_ms']):.1f}")
    print(f"holdout_rmse_ms: {float(aggregate['holdout_rmse_ms']):.1f}")
    print(f"train_validation_gap_mae_ms: {float(aggregate['train_validation_gap_mae_ms']):.1f}")
    print(f"feature_set: {args.feature_set}")
    print("hyperparameters:")
    for key, value in sorted(selected.hyperparameters.items()):
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
