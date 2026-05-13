#!/usr/bin/env python
"""Run controlled XGBoost feature ablations on temporal folds."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from pitwall.ml.ablation import DEFAULT_ABLATION_REPORT_PATH, run_feature_ablations, write_ablation_report
from pitwall.ml.train import DEFAULT_DATASET_METADATA_PATH, DEFAULT_DATASET_PATH, default_hyperparameters, load_dataset
from pitwall.ml.tuning import DEFAULT_TUNING_REPORT_PATH, load_selected_tuning_config

logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--dataset-meta", type=Path, default=DEFAULT_DATASET_METADATA_PATH)
    parser.add_argument("--tuning-report", type=Path, default=DEFAULT_TUNING_REPORT_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_ABLATION_REPORT_PATH)
    parser.add_argument("--rounds", type=int, default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    frame, metadata = load_dataset(args.dataset, args.dataset_meta)
    selected = load_selected_tuning_config(args.tuning_report)
    params = selected[0] if selected else default_hyperparameters()
    rounds = args.rounds or (selected[1] if selected else 100)
    report = run_feature_ablations(
        frame,
        metadata,
        hyperparameters=params,
        num_boost_round=rounds,
    )
    write_ablation_report(report, args.report)
    best = report["best_ablation"]
    logger.info("wrote feature ablation report to %s", args.report)
    print(f"Wrote {args.report}")
    print(
        "best_ablation: "
        f"{best['ablation']} mae_ms={float(best['holdout_mae_ms']):.1f} "
        f"improvement_vs_zero_mae_ms={float(best['improvement_vs_zero_mae_ms']):.1f}"
    )
    for row in report["results"]:
        aggregate = row["aggregate_metrics"]
        print(
            f"{row['ablation']}: mae_ms={float(aggregate['holdout_mae_ms']):.1f} "
            f"rmse_ms={float(aggregate['holdout_rmse_ms']):.1f} "
            f"improvement_vs_zero_mae_ms={float(aggregate['improvement_vs_zero_mae_ms']):.1f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

