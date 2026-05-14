#!/usr/bin/env python
"""Run Phase 6 DoWhy prototype effects over the causal dataset."""

from __future__ import annotations

import argparse
from pathlib import Path

from pitwall.causal.estimators import (
    DEFAULT_DATASET_PATH,
    estimate_default_effects,
    load_causal_dataset,
)


def main() -> int:
    args = parse_args()
    data = load_causal_dataset(args.dataset_path)
    estimates = estimate_default_effects(data)
    print("DoWhy causal undercut prototype")
    print(f"dataset={args.dataset_path}")
    print()
    print("treatment | outcome | method | n_rows | estimate")
    print("----------+---------+--------+--------+---------")
    for estimate in estimates:
        print(
            f"{estimate.treatment} | {estimate.outcome} | {estimate.method_name} | "
            f"{estimate.n_rows} | {estimate.estimate_value:.6f}"
        )
    print()
    print("Notes")
    print("- Binary outcomes are linear probability estimates in this MVP.")
    print("- Demo-race linear models may be ill-conditioned; Phase 7 adds refuters.")
    print("- XGBoost predictions/features/importances are not used.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-path", type=Path, default=DEFAULT_DATASET_PATH)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
