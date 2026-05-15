#!/usr/bin/env python
"""Compare causal_scipy, scipy_engine, and xgb_engine decisions."""

from __future__ import annotations

import argparse
from pathlib import Path

from pitwall.causal.comparison import (
    DEFAULT_COMPARISON_PATH,
    build_disagreement_table,
    load_dataset_for_comparison,
    summarize_disagreements,
    write_disagreement_table,
)
from pitwall.causal.estimators import DEFAULT_DATASET_PATH


def main() -> int:
    args = parse_args()
    data = load_dataset_for_comparison(args.dataset_path)
    table = build_disagreement_table(data)
    summary = summarize_disagreements(table)
    write_disagreement_table(table, args.output)

    print("Causal engine disagreement summary")
    print(f"dataset={args.dataset_path}")
    print(f"output={args.output}")
    print()
    print("metric | value")
    print("-------+------")
    print(f"rows | {summary.row_count}")
    print(f"causal_vs_scipy_comparable_rows | {summary.comparable_scipy_rows}")
    print(f"causal_vs_scipy_disagreements | {summary.causal_vs_scipy_disagreements}")
    print(f"xgb_status | {summary.xgb_status}")
    print(f"causal_vs_xgb_comparable_rows | {summary.comparable_xgb_rows}")
    print(f"causal_vs_xgb_disagreements | {summary.causal_vs_xgb_disagreements}")
    print(f"scipy_vs_xgb_disagreements | {summary.scipy_vs_xgb_disagreements}")
    print()
    print("Notes")
    print("- XGBoost is reported as not evaluated when the dataset has no xgb_engine_decision.")
    print("- This command reads causal dataset outputs and does not modify XGBoost files.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-path", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_COMPARISON_PATH)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
