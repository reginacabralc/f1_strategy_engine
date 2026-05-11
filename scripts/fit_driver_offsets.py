#!/usr/bin/env python
"""Estimate driver pace offsets from clean-air laps and persist to DB."""

from __future__ import annotations

from collections.abc import Iterable

from pitwall.db.engine import create_db_engine
from pitwall.degradation.dataset import refresh_clean_air_lap_times
from pitwall.pace_offsets.estimation import compute_driver_offsets, load_clean_laps
from pitwall.pace_offsets.models import DriverOffsetResult
from pitwall.pace_offsets.writer import write_driver_offsets


def main() -> int:
    engine = create_db_engine()
    with engine.begin() as connection:
        refresh_clean_air_lap_times(connection)
        rows = load_clean_laps(connection)
        results = compute_driver_offsets(rows)
        written = write_driver_offsets(connection, results)

    fitted = [r for r in results if r.status == "fitted"]
    skipped = [r for r in results if r.status != "fitted"]
    print(
        f"Loaded {len(rows)} clean-air laps. "
        f"Fitted {written} offsets, skipped {len(skipped)} (insufficient data)."
    )
    print_offset_table(fitted)
    return 0


def print_offset_table(results: Iterable[DriverOffsetResult]) -> None:
    rows = [
        {
            "driver_code": r.driver_code,
            "circuit_id": r.circuit_id,
            "compound": r.compound,
            "offset_ms": f"{r.offset_ms:+.1f}" if r.offset_ms is not None else "--",
            "n_samples": str(r.n_samples),
            "iqr_ms": f"{r.iqr_ms:.1f}" if r.iqr_ms is not None else "--",
        }
        for r in results
    ]
    if not rows:
        print("No offsets fitted.")
        return
    columns = ["driver_code", "circuit_id", "compound", "offset_ms", "n_samples", "iqr_ms"]
    widths = {
        col: max(len(col), *(len(row.get(col, "")) for row in rows))
        for col in columns
    }
    print(" | ".join(col.ljust(widths[col]) for col in columns))
    print("-+-".join("-" * widths[col] for col in columns))
    for row in rows:
        print(" | ".join(str(row.get(col, "")).ljust(widths[col]) for col in columns))


if __name__ == "__main__":
    raise SystemExit(main())
