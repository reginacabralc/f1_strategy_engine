"""CLI orchestration for one-round FastF1 ingestion."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from pitwall.db.engine import create_db_engine
from pitwall.ingest.fastf1_client import load_race_session
from pitwall.ingest.normalize import (
    build_session_id,
    normalize_drivers,
    normalize_laps,
    normalize_metadata,
    normalize_pit_stops,
    normalize_weather,
    reconstruct_stints,
)
from pitwall.ingest.writer import DatabaseWriter, ProcessedFileWriter, WriteSummary

DEFAULT_YEAR = 2024
DEFAULT_ROUND = 8
DEFAULT_SESSION = "R"


def build_parser() -> argparse.ArgumentParser:
    load_dotenv_file()
    parser = argparse.ArgumentParser(
        description="Ingest one FastF1 race/session into normalized local outputs."
    )
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR)
    parser.add_argument("--round", dest="round_number", type=int, default=DEFAULT_ROUND)
    parser.add_argument("--session", default=DEFAULT_SESSION)
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(os.environ.get("PITWALL_PROCESSED_DIR", "data/processed")),
    )
    parser.add_argument(
        "--mode",
        choices=("dry-run", "database"),
        default="dry-run",
        help="write mode; dry-run writes parquet/json files, database writes Postgres rows.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_const",
        const="dry-run",
        dest="mode",
        help="alias for --mode dry-run",
    )
    parser.add_argument(
        "--write-db",
        action="store_const",
        const="database",
        dest="mode",
        help="alias for --mode database",
    )
    return parser


def build_normalized_outputs(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    session_data = load_race_session(
        year=args.year,
        round_number=args.round_number,
        session_code=args.session,
        cache_dir=args.cache_dir,
    )
    session_id = build_session_id(session_data.event, args.year, args.session)
    laps = normalize_laps(
        session_data.laps,
        session_id=session_id,
        session_start=session_data.session_start,
    )
    stints = reconstruct_stints(laps)
    drivers = normalize_drivers(session_data.results, session_id=session_id)
    weather = normalize_weather(
        session_data.weather,
        session_id=session_id,
        session_start=session_data.session_start,
    )
    pit_stops = normalize_pit_stops(laps)
    metadata = normalize_metadata(
        session_id=session_id,
        year=args.year,
        round_number=args.round_number,
        session_code=args.session,
        event=session_data.event,
        session_start=session_data.session_start,
        total_laps=max((int(row["lap_number"]) for row in laps), default=None),
    )

    outputs: dict[str, Any] = {
        "metadata": metadata,
        "drivers": drivers,
        "laps": laps,
        "stints": stints,
        "pit_stops": pit_stops,
        "weather": weather,
    }
    return session_id, outputs


def ingest_one_round(args: argparse.Namespace) -> WriteSummary:
    session_id, outputs = build_normalized_outputs(args)
    if args.mode == "database":
        return DatabaseWriter(create_db_engine()).write_session(outputs)
    return ProcessedFileWriter(args.output_dir).write_session(session_id, outputs)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    summary = ingest_one_round(args)
    if summary.output_dir is not None:
        print(f"Wrote normalized outputs to {summary.output_dir}")
    else:
        print("Wrote normalized outputs to database")
    for name, count in sorted(summary.counts.items()):
        print(f"{name}: {count}")
    return 0


def load_dotenv_file() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()
