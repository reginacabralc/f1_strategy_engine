#!/usr/bin/env python
"""Train the Day 8 native XGBoost pace model."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from pitwall.ml.ablation import resolve_ablation_feature_columns
from pitwall.ml.train import (
    DEFAULT_DATASET_METADATA_PATH,
    DEFAULT_DATASET_PATH,
    DEFAULT_MODEL_METADATA_PATH,
    DEFAULT_MODEL_PATH,
    TargetClipConfig,
    format_feature_importances,
    format_fold_metrics,
    format_target_distributions,
    train_xgb_model,
)
from pitwall.ml.tuning import DEFAULT_TUNING_REPORT_PATH, load_selected_tuning_config


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--dataset-meta", type=Path, default=DEFAULT_DATASET_METADATA_PATH)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--model-meta", type=Path, default=DEFAULT_MODEL_METADATA_PATH)
    parser.add_argument("--tuning-report", type=Path, default=DEFAULT_TUNING_REPORT_PATH)
    parser.add_argument("--ignore-tuning-report", action="store_true")
    parser.add_argument("--rounds", type=int, default=None)
    parser.add_argument("--feature-set", default=os.getenv("FEATURE_SET", "full"))
    parser.add_argument(
        "--target-clip-quantiles",
        default=os.getenv("TARGET_CLIP_QUANTILES", ""),
        help="Optional lower,upper quantiles for winsorized training labels, e.g. 0.01,0.99.",
    )
    args = parser.parse_args()
    selected_config = None if args.ignore_tuning_report else load_selected_tuning_config(args.tuning_report)
    selected_params = selected_config[0] if selected_config else None
    selected_rounds = selected_config[1] if selected_config else None
    num_boost_round = args.rounds or selected_rounds or 250
    feature_columns = resolve_ablation_feature_columns(args.feature_set)

    result = train_xgb_model(
        dataset_path=args.dataset,
        dataset_metadata_path=args.dataset_meta,
        model_path=args.model,
        metadata_path=args.model_meta,
        hyperparameters=selected_params,
        num_boost_round=num_boost_round,
        feature_columns=feature_columns,
        feature_set_name=args.feature_set,
        target_clip_config=_parse_clip_config(args.target_clip_quantiles),
    )

    metadata = result.metadata
    print("fold diagnostics:")
    print(format_fold_metrics(metadata["fold_metrics"]))
    print()
    print("holdout target distributions:")
    print(format_target_distributions(metadata["fold_metrics"]))
    print()
    print("top feature importances by gain:")
    print(format_feature_importances(metadata["top_feature_importances"]))
    aggregate = metadata["aggregate_metrics"]
    print()
    print("aggregate:")
    print(f"  feature_set: {args.feature_set}")
    print(f"  rows: {aggregate['holdout_rows']}")
    print(f"  train_mae_ms: {aggregate['train_mae_ms']:.1f}")
    print(f"  train_rmse_ms: {aggregate['train_rmse_ms']:.1f}")
    print(f"  train_r2: {aggregate['train_r2']:.3f}")
    print(f"  holdout_mae_ms: {aggregate['holdout_mae_ms']:.1f}")
    print(f"  holdout_rmse_ms: {aggregate['holdout_rmse_ms']:.1f}")
    print(f"  holdout_r2: {aggregate['holdout_r2']:.3f}")
    print(f"  zero_holdout_mae_ms: {aggregate['zero_holdout_mae_ms']:.1f}")
    print(f"  train_mean_holdout_mae_ms: {aggregate['train_mean_holdout_mae_ms']:.1f}")
    print(f"  improvement_vs_zero_mae_ms: {aggregate['improvement_vs_zero_mae_ms']:.1f}")
    print(f"  overfitting_diagnosis: {metadata['overfitting_diagnosis']}")
    print(f"  diagnosis: {metadata['diagnosis']}")
    if selected_params:
        print(f"  hyperparameters_source: {args.tuning_report}")
    print(f"  target_transform: {metadata['target_transform']['strategy']}")
    print()
    print(f"Wrote {result.model_path}")
    print(f"Wrote {result.metadata_path}")
    return 0


def _parse_clip_config(value: str) -> TargetClipConfig | None:
    if not value.strip():
        return None
    lower, upper = (float(item.strip()) for item in value.split(",", maxsplit=1))
    return TargetClipConfig(lower_quantile=lower, upper_quantile=upper)


if __name__ == "__main__":
    raise SystemExit(main())
