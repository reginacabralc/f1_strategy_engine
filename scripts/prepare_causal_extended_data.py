#!/usr/bin/env python
"""Prepare an extended multi-race causal dataset from FastF1 sessions."""

from __future__ import annotations

import argparse
import subprocess

DEFAULT_RACES: tuple[tuple[int, int], ...] = (
    (2023, 1),
    (2023, 6),
    (2023, 12),
    (2023, 19),
    (2024, 1),
    (2024, 8),
    (2024, 13),
    (2024, 20),
)


def main() -> int:
    args = parse_args()
    races = tuple(_parse_race(value) for value in args.race) or DEFAULT_RACES
    for year, round_number in races:
        _run(
            [
                args.python,
                "scripts/ingest_season.py",
                "--year",
                str(year),
                "--round",
                str(round_number),
                "--session",
                args.session,
                "--write-db",
            ],
            dry_run=args.dry_run,
        )
    for command in (
        [args.make, "reconstruct-race-gaps"],
        [args.python, "scripts/fit_degradation.py", "--all-sessions"],
        [args.python, "scripts/fit_pit_loss.py"],
        [args.python, "scripts/fit_driver_offsets.py"],
        [args.make, "derive-known-undercuts"],
        [args.make, "import-curated-known-undercuts"],
        [args.make, "build-causal-dataset"],
        [args.make, "run-causal-dowhy"],
        [args.make, "compare-causal-engines"],
    ):
        _run(command, dry_run=args.dry_run)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--race",
        action="append",
        default=[],
        help="Race to ingest as YEAR:ROUND, e.g. 2024:1. Repeatable.",
    )
    parser.add_argument("--session", default="R")
    parser.add_argument("--python", default=".venv/bin/python")
    parser.add_argument("--make", default="make")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _parse_race(value: str) -> tuple[int, int]:
    try:
        year_text, round_text = value.split(":", 1)
        return int(year_text), int(round_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"race must be YEAR:ROUND, got {value!r}"
        ) from exc


def _run(command: list[str], *, dry_run: bool) -> None:
    print("+ " + " ".join(command))
    if dry_run:
        return
    subprocess.run(command, check=True)


if __name__ == "__main__":
    raise SystemExit(main())
