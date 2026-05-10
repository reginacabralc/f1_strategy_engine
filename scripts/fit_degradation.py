#!/usr/bin/env python
"""Fit quadratic tyre degradation coefficients from the local demo DB."""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Iterable
from typing import Any

from pitwall.db.engine import create_db_engine
from pitwall.degradation.dataset import (
    DEMO_SESSION_IDS,
    read_clean_lap_dataset,
    refresh_clean_air_lap_times,
)
from pitwall.degradation.fit import fit_degradation
from pitwall.degradation.models import DegradationFitResult
from pitwall.degradation.writer import write_fit_results


def main() -> int:
    args = parse_args()
    session_ids = DEMO_SESSION_IDS if args.all_demo else ()
    session_id = None if args.all_demo else args.session

    engine = create_db_engine()
    with engine.begin() as connection:
        if args.refresh_clean_air:
            refresh_clean_air_lap_times(connection)
        rows = read_clean_lap_dataset(
            connection,
            session_id=session_id,
            session_ids=session_ids,
        )
        results = fit_degradation(rows)
        written = write_fit_results(connection, results)

    print(
        f"Read {len(rows)} clean-air diagnostic rows; wrote {written} coefficient rows."
    )
    print_eligibility_summary(rows)
    print_fit_table(results)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group()
    target.add_argument(
        "--session",
        default="monaco_2024_R",
        help="Session id to fit when --all-demo is not provided (default: monaco_2024_R).",
    )
    target.add_argument(
        "--all-demo",
        action="store_true",
        help="Fit Bahrain, Monaco, and Hungary 2024 race sessions.",
    )
    parser.add_argument(
        "--no-refresh-clean-air",
        dest="refresh_clean_air",
        action="store_false",
        help="Skip refreshing clean_air_lap_times before fitting.",
    )
    parser.set_defaults(refresh_clean_air=True)
    return parser.parse_args()


def print_eligibility_summary(rows: Iterable[dict[str, Any]]) -> None:
    rows = list(rows)
    reasons = Counter(str(row.get("exclusion_reason") or "eligible") for row in rows)
    pieces = [f"{reason}={count}" for reason, count in sorted(reasons.items())]
    print("Eligibility: " + ", ".join(pieces))


def print_fit_table(results: Iterable[DegradationFitResult]) -> None:
    rows = [
        {
            "session/circuit": result.circuit_id,
            "compound": result.compound,
            "n_laps": result.n_laps,
            "R2": _format_metric(result.r2, digits=2),
            "RMSE_ms": _format_metric(result.rmse_ms, digits=0),
            "status": result.status,
        }
        for result in results
    ]
    print_table(
        rows, ["session/circuit", "compound", "n_laps", "R2", "RMSE_ms", "status"]
    )


def print_table(rows: list[dict[str, Any]], columns: list[str]) -> None:
    widths = {
        column: max(len(column), *(len(str(row.get(column, ""))) for row in rows))
        for column in columns
    }
    print(" | ".join(column.ljust(widths[column]) for column in columns))
    print("-+-".join("-" * widths[column] for column in columns))
    for row in rows:
        print(
            " | ".join(
                str(row.get(column, "")).ljust(widths[column]) for column in columns
            )
        )


def _format_metric(value: float | None, *, digits: int) -> str:
    return "--" if value is None else f"{value:.{digits}f}"


if __name__ == "__main__":
    raise SystemExit(main())
