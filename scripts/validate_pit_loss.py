#!/usr/bin/env python
"""Validate persisted pit-loss estimates in the local DB."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pitwall.db.engine import create_db_engine
from pitwall.engine.pit_loss import lookup_pit_loss
from pitwall.pit_loss.estimation import (
    PitLossEstimate,
    build_pit_loss_report_rows,
    load_pit_loss_estimates,
    load_pit_loss_samples,
    load_pit_loss_table,
    validate_pit_loss_estimates,
)


def main() -> int:
    engine = create_db_engine()
    with engine.connect() as connection:
        estimates = load_pit_loss_estimates(connection)
        validate_pit_loss_estimates(estimates)
        samples = load_pit_loss_samples(connection)
        report_rows = build_pit_loss_report_rows(samples)
        table = load_pit_loss_table(connection)

    print("Pit-loss estimates")
    print_table(
        report_rows or [_estimate_to_row(row) for row in estimates],
        [
            "circuit_id",
            "team_code",
            "pit_loss_ms",
            "n_samples",
            "iqr_ms",
            "std_ms",
            "min_ms",
            "max_ms",
            "aggregation_method",
            "source",
            "quality",
            "status",
        ],
    )
    print("\nEngine lookup smoke")
    for circuit_id in sorted(table):
        fallback = lookup_pit_loss(circuit_id, "__missing_team__", table)
        print(f"{circuit_id}: fallback={fallback} ms")
    return 0


def print_table(rows: Iterable[dict[str, Any]], columns: list[str]) -> None:
    rows = list(rows)
    widths = {
        column: max([len(column), *(len(str(row.get(column, ""))) for row in rows)])
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


def _estimate_to_row(row: PitLossEstimate) -> dict[str, Any]:
    return {
        "circuit_id": row.circuit_id,
        "team_code": row.team_code if row.team_code is not None else "<circuit>",
        "pit_loss_ms": row.pit_loss_ms,
        "n_samples": row.n_samples,
    }


if __name__ == "__main__":
    raise SystemExit(main())
