#!/usr/bin/env python
"""Evaluate offline pair-level undercut challenger models."""

from __future__ import annotations

import argparse
from pathlib import Path

from pitwall.ml.undercut_challenger import (
    DEFAULT_CHALLENGER_REPORT_PATH,
    DEFAULT_PAIR_DATASET_PATH,
    evaluate_pair_level_challengers,
    load_pair_dataset,
    write_challenger_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_PAIR_DATASET_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_CHALLENGER_REPORT_PATH)
    parser.add_argument("--validation-fraction", type=float, default=0.30)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    frame = load_pair_dataset(args.dataset)
    report = evaluate_pair_level_challengers(
        frame,
        validation_fraction=args.validation_fraction,
        random_seed=args.seed,
    )
    write_challenger_report(report, args.report)
    xgb = report["xgboost_proxy_metrics"]
    observed = report["xgboost_observed_success_metrics"]
    rf = report["random_forest_proxy_metrics"]
    print(f"Wrote {args.report}")
    print(
        "xgboost_proxy: "
        f"rows={xgb['rows']} precision={xgb['precision']:.3f} "
        f"recall={xgb['recall']:.3f} f1={xgb['f1']:.3f} "
        f"brier={xgb['brier_score']:.3f}"
    )
    print(f"xgboost_observed_success_status: {observed['status']}")
    print(f"random_forest_status: {rf['status']}")
    print(f"selected_runtime_action: {report['selected_runtime_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
