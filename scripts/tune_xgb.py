#!/usr/bin/env python
"""Tune XGBoost hyperparameters on temporal validation folds."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from pitwall.ml.ablation import resolve_ablation_feature_columns
from pitwall.ml.train import (
    DEFAULT_DATASET_METADATA_PATH,
    DEFAULT_DATASET_PATH,
    TargetClipConfig,
    load_dataset,
)
from pitwall.ml.tuning import DEFAULT_TUNING_REPORT_PATH, tune_xgb_hyperparameters


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--dataset-meta", type=Path, default=DEFAULT_DATASET_METADATA_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_TUNING_REPORT_PATH)
    parser.add_argument("--rounds", type=int, default=200)
    parser.add_argument("--feature-set", default=os.getenv("FEATURE_SET", "full"))
    parser.add_argument("--random-candidates", type=int, default=12)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--target-clip-quantiles",
        default=os.getenv("TARGET_CLIP_QUANTILES", ""),
        help="Optional lower,upper quantiles for winsorized training labels, e.g. 0.01,0.99.",
    )
    args = parser.parse_args()

    frame, metadata = load_dataset(args.dataset, args.dataset_meta)
    feature_columns = resolve_ablation_feature_columns(args.feature_set)
    result = tune_xgb_hyperparameters(
        frame,
        metadata,
        num_boost_round=args.rounds,
        feature_columns=feature_columns,
        random_candidates=args.random_candidates,
        seed=args.seed,
        target_clip_config=_parse_clip_config(args.target_clip_quantiles),
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
    print(f"random_candidates: {args.random_candidates}")
    print(f"seed: {args.seed}")
    print("hyperparameters:")
    for key, value in sorted(selected.hyperparameters.items()):
        print(f"  {key}: {value}")
    return 0


def _parse_clip_config(value: str) -> TargetClipConfig | None:
    if not value.strip():
        return None
    lower, upper = (float(item.strip()) for item in value.split(",", maxsplit=1))
    return TargetClipConfig(lower_quantile=lower, upper_quantile=upper)


if __name__ == "__main__":
    raise SystemExit(main())
