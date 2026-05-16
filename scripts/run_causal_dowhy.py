#!/usr/bin/env python
"""Run Phase 6 DoWhy prototype effects over the causal dataset."""

from __future__ import annotations

import argparse
from pathlib import Path

from pitwall.causal.estimators import (
    DEFAULT_DATASET_PATH,
    estimate_default_effects_with_refuters,
    load_causal_dataset,
)


def main() -> int:
    args = parse_args()
    data = load_causal_dataset(args.dataset_path)
    results = estimate_default_effects_with_refuters(data)
    print("DoWhy causal undercut prototype + refuters")
    print(f"dataset={args.dataset_path}")
    print()
    print("treatment | outcome | method | n_rows | estimate")
    print("----------+---------+--------+--------+---------")
    for result in results:
        estimate = result.estimate
        print(
            f"{estimate.treatment} | {estimate.outcome} | {estimate.method_name} | "
            f"{estimate.n_rows} | {estimate.estimate_value:.6f}"
        )
        for refutation in result.refutations:
            refuted = (
                "n/a"
                if refutation.refuted_estimate is None
                else f"{refutation.refuted_estimate:.6f}"
            )
            delta = "n/a" if refutation.delta is None else f"{refutation.delta:.6f}"
            print(
                f"  refuter={refutation.refuter_name} | "
                f"refuted={refuted} | delta={delta} | "
                f"stability={refutation.stability}"
            )
    print()
    print("Notes")
    print("- Binary outcomes are linear probability estimates in this MVP.")
    print("- Refuters are sensitivity checks, not proof of true causal validity.")
    print("- Demo-race linear models may be ill-conditioned; unstable effects need more data.")
    print("- XGBoost predictions/features/importances are not used.")

    from pitwall.causal.estimators import estimate_stratified_effects, stratified_effect_specs

    stratified = estimate_stratified_effects(data, stratified_effect_specs())
    ran = [(spec, est) for spec, est in stratified if est is not None]
    if ran:
        print()
        print("Stratified effects by circuit")
        print(f"{'circuit':<18} {'treatment':<25} {'n_rows':>7} {'estimate':>12}")
        print("-" * 66)
        for spec, est in ran:
            print(
                f"{spec.circuit_filter:<18} {spec.treatment:<25} "
                f"{est.n_rows:>7} {est.estimate_value:>12.6f}"
            )
    else:
        print()
        print("Stratified effects: all circuits have < 200 rows, skipped.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-path", type=Path, default=DEFAULT_DATASET_PATH)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
