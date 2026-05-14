#!/usr/bin/env python
"""Populate known_undercuts from observed pit-cycle exchanges."""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Iterable
from typing import Any

from pitwall.causal.known_undercuts import (
    KnownUndercut,
    derive_known_undercuts,
    load_lap_cycle_inputs,
    write_known_undercuts,
)
from pitwall.db.engine import create_db_engine


def main() -> int:
    args = parse_args()
    session_ids = tuple(args.session_id)
    engine = create_db_engine()
    with engine.begin() as connection:
        rows = load_lap_cycle_inputs(connection, session_ids=session_ids)
        candidates = derive_known_undercuts(
            rows,
            max_pre_pit_gap_ms=args.max_pre_pit_gap_ms,
            max_defender_response_laps=args.max_defender_response_laps,
            eval_settle_laps=args.eval_settle_laps,
        )
        written = 0 if args.dry_run else write_known_undercuts(connection, candidates)

    action = "Would write" if args.dry_run else "Wrote"
    print(f"{action} {written if not args.dry_run else len(candidates)} known undercut rows.")
    print_summary(candidates)
    print()
    print("Notes")
    print("- Rows are auto-derived from observed pit-cycle exchanges, not human curated.")
    print("- Manual curated rows are preserved; only previous auto-derived rows are replaced.")
    print("- Source is encoded in notes with prefix auto_derived_pit_cycle_v1.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--session-id",
        action="append",
        default=[],
        help="Restrict derivation to a session_id. Can be passed multiple times.",
    )
    parser.add_argument(
        "--max-pre-pit-gap-ms",
        type=int,
        default=30_000,
        help="Maximum attacker gap to the defender on the pre-pit lap.",
    )
    parser.add_argument(
        "--max-defender-response-laps",
        type=int,
        default=8,
        help="Maximum laps after attacker pit-in for defender pit-in.",
    )
    parser.add_argument(
        "--eval-settle-laps",
        type=int,
        default=1,
        help="Laps after defender pit-out used to evaluate position exchange.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute derived rows without updating the DB.",
    )
    return parser.parse_args()


def print_summary(rows: Iterable[KnownUndercut]) -> None:
    rows = list(rows)
    if not rows:
        print("(no derived undercuts)")
        return
    by_session = Counter(row.session_id for row in rows)
    by_success = Counter(row.was_successful for row in rows)
    print_table(
        [
            {"bucket": "total", "rows": len(rows)},
            {"bucket": "successful", "rows": by_success[True]},
            {"bucket": "unsuccessful", "rows": by_success[False]},
            *[
                {"bucket": session_id, "rows": count}
                for session_id, count in sorted(by_session.items())
            ],
        ],
        ["bucket", "rows"],
    )


def print_table(rows: list[dict[str, Any]], columns: list[str]) -> None:
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
