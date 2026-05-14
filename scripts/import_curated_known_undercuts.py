#!/usr/bin/env python
"""Import manually curated known undercut labels from CSV."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from pitwall.causal.known_undercuts import (
    load_curated_known_undercuts_csv,
    write_curated_known_undercuts,
)
from pitwall.db.engine import create_db_engine

DEFAULT_CURATED_PATH = Path("data/curation/known_undercuts_curated.csv")


def main() -> int:
    args = parse_args()
    rows = load_curated_known_undercuts_csv(args.input)
    written = 0
    if not args.dry_run:
        engine = create_db_engine()
        with engine.begin() as connection:
            written = write_curated_known_undercuts(
                connection,
                rows,
                replace_curated=not args.append,
            )

    action = "Would write" if args.dry_run else "Wrote"
    print(f"{action} {len(rows) if args.dry_run else written} curated known undercut rows.")
    if rows:
        by_session = Counter(row.session_id for row in rows)
        by_success = Counter(row.was_successful for row in rows)
        print(f"successful={by_success[True]} unsuccessful={by_success[False]}")
        for session_id, count in sorted(by_session.items()):
            print(f"{session_id}: {count}")
    else:
        print("No curated rows found. Fill the CSV with manually reviewed cases first.")
    print()
    print("Notes")
    print("- Curated rows use notes prefix curated_manual_v1.")
    print("- Auto-derived rows are preserved.")
    print("- Rebuild the causal dataset after importing curated labels.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_CURATED_PATH)
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append curated rows instead of replacing previous curated_manual_v1 rows.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and summarize the CSV without updating the DB.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
