#!/usr/bin/env python
"""Reconstruct lap-line race gaps into laps.gap_to_* columns."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from typing import Any

from pitwall.causal.gaps import (
    GapSessionSummary,
    load_gap_inputs,
    reconstruct_gap_updates,
    summarize_gap_updates,
    write_gap_updates,
)
from pitwall.db.engine import create_db_engine


def main() -> int:
    args = parse_args()
    session_ids = tuple(args.session_id)
    engine = create_db_engine()
    with engine.begin() as connection:
        rows = load_gap_inputs(connection, session_ids=session_ids)
        updates = reconstruct_gap_updates(rows)
        written = 0 if args.dry_run else write_gap_updates(connection, updates)

    summaries = summarize_gap_updates(updates)
    action = "Would update" if args.dry_run else "Updated"
    print(
        f"{action} {written if not args.dry_run else len(updates)} lap rows "
        "with reconstructed gap columns."
    )
    print_table(
        [
            {
                "session_id": summary.session_id,
                "rows": summary.rows,
                "gap_to_leader_rows": summary.gap_to_leader_rows,
                "gap_to_ahead_rows": summary.gap_to_ahead_rows,
            }
            for summary in summaries
        ],
        ["session_id", "rows", "gap_to_leader_rows", "gap_to_ahead_rows"],
    )
    print_reconstruction_notes(summaries)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--session-id",
        action="append",
        default=[],
        help="Restrict reconstruction to a session_id. Can be passed multiple times.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute reconstruction coverage without updating the DB.",
    )
    return parser.parse_args()


def print_reconstruction_notes(summaries: Iterable[GapSessionSummary]) -> None:
    summaries = list(summaries)
    if not summaries:
        print("No lap rows found.")
        return
    print()
    print("Notes")
    print("- Gaps are reconstructed from FastF1 lap-end timestamps at the lap line.")
    print("- Downstream causal labels must carry gap_source='reconstructed_fastf1_time'.")
    print("- Rows without race position keep gap fields NULL.")


def print_table(rows: list[dict[str, Any]], columns: list[str]) -> None:
    if not rows:
        print("(no rows)")
        return
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


if __name__ == "__main__":
    raise SystemExit(main())
