#!/usr/bin/env python
"""Validate the Day 8 native XGBoost model artifact."""

from __future__ import annotations

import argparse
from pathlib import Path

from pitwall.ml.train import (
    DEFAULT_DATASET_METADATA_PATH,
    DEFAULT_DATASET_PATH,
    DEFAULT_MODEL_METADATA_PATH,
    DEFAULT_MODEL_PATH,
    validate_model_artifacts,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--dataset-meta", type=Path, default=DEFAULT_DATASET_METADATA_PATH)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--model-meta", type=Path, default=DEFAULT_MODEL_METADATA_PATH)
    args = parser.parse_args()

    try:
        summary = validate_model_artifacts(
            model_path=args.model,
            metadata_path=args.model_meta,
            dataset_path=args.dataset,
            dataset_metadata_path=args.dataset_meta,
        )
    except Exception as exc:
        print(f"FAILED: {exc}")
        return 1

    print("XGBoost model validation passed.")
    print(f"model: {summary['model_path']}")
    print(f"metadata: {summary['metadata_path']}")
    print(f"rows: {summary['row_count']}")
    print(f"usable_rows: {summary['usable_row_count']}")
    print(f"feature_count: {summary['feature_count']}")
    print(f"fold_count: {summary['fold_count']}")
    print(f"sessions: {', '.join(summary['sessions'])}")
    aggregate = summary["aggregate_metrics"]
    print(
        "aggregate: "
        f"holdout_mae_ms={aggregate['holdout_mae_ms']:.1f}, "
        f"holdout_rmse_ms={aggregate['holdout_rmse_ms']:.1f}, "
        f"holdout_r2={aggregate['holdout_r2']:.3f}, "
        f"zero_holdout_mae_ms={aggregate['zero_holdout_mae_ms']:.1f}, "
        f"train_mean_holdout_mae_ms={aggregate['train_mean_holdout_mae_ms']:.1f}"
    )
    print(f"diagnosis: {summary['diagnosis']}")
    print("top_feature_importances:")
    for row in summary["top_feature_importances"][:5]:
        print(f"  {row['feature']}: gain={float(row['gain']):.4f}")
    print(f"prediction_sample_size: {summary['prediction_sample_size']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
