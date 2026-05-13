#!/usr/bin/env python
"""Evaluate leakage-safe baseline ladder for the XGBoost pace dataset."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from pitwall.ml.baselines import DEFAULT_BASELINE_REPORT_PATH, evaluate_baseline_ladder, write_baseline_report
from pitwall.ml.train import DEFAULT_DATASET_METADATA_PATH, DEFAULT_DATASET_PATH, load_dataset

logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--dataset-meta", type=Path, default=DEFAULT_DATASET_METADATA_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_BASELINE_REPORT_PATH)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    frame, metadata = load_dataset(args.dataset, args.dataset_meta)
    report = evaluate_baseline_ladder(frame, metadata)
    write_baseline_report(report, args.report)
    best = report.get("best_baseline") or {}
    logger.info("wrote baseline ladder report to %s", args.report)
    print(f"Wrote {args.report}")
    print(
        "best_baseline: "
        f"{best.get('baseline')} mae_ms={float(best.get('mae_ms', 0.0)):.1f}"
    )
    for row in report["aggregate_metrics"]:
        print(
            f"{row['baseline']}: mae_ms={float(row['mae_ms']):.1f} "
            f"rmse_ms={float(row['rmse_ms']):.1f} r2={float(row['r2']):.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

