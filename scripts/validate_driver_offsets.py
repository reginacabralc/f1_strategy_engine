#!/usr/bin/env python
"""Validate persisted driver pace offsets in the local DB."""

from __future__ import annotations

from collections.abc import Iterable
from importlib import import_module
from typing import Any

from pitwall.db.engine import create_db_engine
from pitwall.degradation.dataset import DEMO_SESSION_IDS
from pitwall.pace_offsets.models import MAX_ABSURD_OFFSET_MS

LOAD_OFFSETS_SQL = """
    SELECT
        driver_code,
        circuit_id,
        compound,
        offset_ms,
        n_samples,
        computed_at
    FROM driver_skill_offsets
    ORDER BY circuit_id, compound, driver_code
"""

DEMO_CIRCUITS_SQL = """
    SELECT DISTINCT e.circuit_id
    FROM sessions s
    JOIN events e ON e.event_id = s.event_id
    WHERE s.session_id = ANY(:session_ids)
"""


def main() -> int:
    engine = create_db_engine()
    with engine.connect() as connection:
        rows_raw = connection.execute(_sql_text(LOAD_OFFSETS_SQL))
        offset_rows = [dict(row._mapping) for row in rows_raw]
        circuits_raw = connection.execute(
            _sql_text(DEMO_CIRCUITS_SQL), {"session_ids": list(DEMO_SESSION_IDS)}
        )
        demo_circuits = {row._mapping["circuit_id"] for row in circuits_raw}

    errors = validate(offset_rows, demo_circuits)
    print_table(offset_rows)

    if errors:
        print(f"\nFAILED: {len(errors)} validation error(s):")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(f"\nOK: {len(offset_rows)} offsets validated successfully.")
    return 0


def validate(rows: list[dict[str, Any]], demo_circuits: set[str]) -> list[str]:
    errors: list[str] = []
    if not rows:
        errors.append("no offsets found — run make fit-driver-offsets first")
        return errors

    fitted_circuits = {str(row["circuit_id"]) for row in rows}
    missing = demo_circuits - fitted_circuits
    if missing:
        errors.append(
            f"demo circuit(s) produced zero usable offsets: {', '.join(sorted(missing))}"
        )

    for row in rows:
        offset_ms = row.get("offset_ms")
        key = f"{row['driver_code']}/{row['circuit_id']}/{row['compound']}"
        if offset_ms is None:
            errors.append(f"offset_ms is NULL for {key}")
        elif abs(float(offset_ms)) > MAX_ABSURD_OFFSET_MS:
            errors.append(f"absurd offset_ms={float(offset_ms):.0f} ms for {key}")
    return errors


def print_table(rows: Iterable[dict[str, Any]]) -> None:
    columns = ["driver_code", "circuit_id", "compound", "offset_ms", "n_samples", "status"]
    display_rows = [
        {
            "driver_code": str(row.get("driver_code", "")),
            "circuit_id": str(row.get("circuit_id", "")),
            "compound": str(row.get("compound", "")),
            "offset_ms": (
                f"{float(row['offset_ms']):+.1f}"
                if row.get("offset_ms") is not None
                else "NULL"
            ),
            "n_samples": str(row.get("n_samples", "")),
            "status": (
                "ok"
                if row.get("offset_ms") is not None
                and abs(float(row["offset_ms"])) <= MAX_ABSURD_OFFSET_MS
                else "absurd"
            ),
        }
        for row in rows
    ]
    if not display_rows:
        print("(no offsets to display)")
        return
    widths = {
        col: max(len(col), *(len(row.get(col, "")) for row in display_rows))
        for col in columns
    }
    print(" | ".join(col.ljust(widths[col]) for col in columns))
    print("-+-".join("-" * widths[col] for col in columns))
    for row in display_rows:
        print(" | ".join(str(row.get(col, "")).ljust(widths[col]) for col in columns))


def _sql_text(sql: str) -> Any:
    sqlalchemy = import_module("sqlalchemy")
    return sqlalchemy.text(sql)


if __name__ == "__main__":
    raise SystemExit(main())
