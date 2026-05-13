#!/usr/bin/env python
"""Validate the multi-season ML race manifest."""

from __future__ import annotations

import argparse
from pathlib import Path

from pitwall.ingest.fastf1_client import enable_fastf1_cache
from pitwall.ingest.manifest import DEFAULT_MANIFEST_PATH, load_race_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument(
        "--strict-schedule",
        action="store_true",
        help="fail when FastF1 schedule introspection is unavailable or missing an entry",
    )
    args = parser.parse_args()

    manifest = load_race_manifest(args.manifest)
    enabled = manifest.enabled_entries()
    disabled = manifest.disabled_entries()
    future = manifest.skipped_future_entries()

    print(f"Manifest: {args.manifest}")
    print(f"as_of_date: {manifest.as_of_date}")
    print(f"enabled ingestable races: {len(enabled)}")
    print(f"disabled races: {len(disabled)}")
    print(f"future enabled races skipped by date: {len(future)}")
    for entry in enabled:
        print(f"  enabled: {entry.year} R{entry.round_number:02d} {entry.session} {entry.display_label}")
    for entry in future:
        print(f"  future: {entry.year} R{entry.round_number:02d} {entry.session} {entry.display_label}")

    schedule_errors = _schedule_errors(manifest.entries)
    if schedule_errors:
        print("FastF1 schedule warnings:")
        for error in schedule_errors:
            print(f"  - {error}")
        return 1 if args.strict_schedule else 0
    print("FastF1 schedule check passed.")
    return 0


def _schedule_errors(entries: object) -> list[str]:
    try:
        import fastf1
    except ImportError:
        return ["FastF1 is not installed"]
    enable_fastf1_cache()
    try:
        fastf1.Cache.offline_mode(True)
    except AttributeError:
        pass

    errors: list[str] = []
    years = sorted({entry.year for entry in entries})  # type: ignore[attr-defined]
    schedules: dict[int, set[int]] = {}
    for year in years:
        try:
            schedule = fastf1.get_event_schedule(year, include_testing=False)
        except Exception as exc:
            errors.append(f"{year}: schedule unavailable: {exc}")
            continue
        schedules[year] = {int(value) for value in schedule["RoundNumber"].dropna().to_list()}
    for entry in entries:  # type: ignore[assignment]
        if entry.year in schedules and entry.round_number not in schedules[entry.year]:
            errors.append(f"{entry.year} round {entry.round_number} not present in FastF1 schedule")
    return errors


if __name__ == "__main__":
    raise SystemExit(main())
