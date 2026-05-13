#!/usr/bin/env python
"""Ingest enabled races from the ML race manifest."""

from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

from pitwall.ingest.cli import ingest_one_round, load_dotenv_file
from pitwall.ingest.manifest import (
    DEFAULT_MANIFEST_PATH,
    DEFAULT_REPORT_PATH,
    RaceManifestEntry,
    ingest_manifest_entries,
    load_race_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--continue-on-error", action="store_true")
    args = parser.parse_args()

    load_dotenv_file()
    manifest = load_race_manifest(args.manifest)

    def ingest_entry(entry: RaceManifestEntry) -> dict[str, int]:
        summary = ingest_one_round(
            SimpleNamespace(
                year=entry.year,
                round_number=entry.round_number,
                session=entry.session,
                cache_dir=args.cache_dir,
                output_dir=Path("data/processed"),
                mode="database",
            )
        )
        return dict(summary.counts)

    report = ingest_manifest_entries(
        manifest.entries,
        ingest_entry=ingest_entry,
        as_of_date=manifest.as_of_date,
        continue_on_error=args.continue_on_error,
    )
    report.write_json(args.report)

    print(f"Wrote {args.report}")
    print(
        "summary: "
        f"attempted={report.summary['attempted']} "
        f"succeeded={report.summary['succeeded']} "
        f"skipped={report.summary['skipped']} "
        f"failed={report.summary['failed']}"
    )
    for item in report.items:
        print(
            f"  {item.status.value}: {item.entry.year} R{item.entry.round_number:02d} "
            f"{item.entry.session} {item.entry.display_label}"
            + (f" ({item.reason})" if item.reason else "")
            + (f" ERROR: {item.error}" if item.error else "")
        )
    return 1 if report.summary["failed"] and not args.continue_on_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
