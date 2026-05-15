#!/usr/bin/env python
"""Build the Phase 3/4 causal undercut driver-rival-lap dataset."""

from __future__ import annotations

import argparse
from pathlib import Path

from pitwall.causal.dataset_builder import (
    DEFAULT_CURATED_VIABILITY_PATH,
    build_causal_dataset_from_db,
    load_curated_viability_labels_csv,
    write_causal_dataset,
)
from pitwall.db.engine import create_db_engine

DEFAULT_DATASET_PATH = Path("data/causal/undercut_driver_rival_lap.parquet")
DEFAULT_METADATA_PATH = Path("data/causal/undercut_driver_rival_lap.meta.json")


def main() -> int:
    args = parse_args()
    curated_viability_labels = load_curated_viability_labels_csv(
        args.curated_viability_labels
    )
    engine = create_db_engine()
    with engine.connect() as connection:
        result = build_causal_dataset_from_db(
            connection,
            session_ids=tuple(args.session_id),
            curated_viability_labels=curated_viability_labels,
        )
    write_causal_dataset(
        result,
        dataset_path=args.dataset_path,
        metadata_path=args.metadata_path,
    )
    print(
        f"Wrote {len(result.rows)} causal driver-rival-lap rows to "
        f"{args.dataset_path}."
    )
    print(f"Metadata: {args.metadata_path}")
    print(
        "Usable rows: "
        f"{result.metadata['usable_row_count']} / {result.metadata['row_count']}; "
        f"viable rows: {result.metadata['undercut_viable_rows']}; "
        f"curated viability rows: {result.metadata['curated_viability_rows']}; "
        f"observed success rows: {result.metadata['observed_success_rows']}"
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--session-id",
        action="append",
        default=[],
        help="Restrict build to a session_id. Can be passed multiple times.",
    )
    parser.add_argument("--dataset-path", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--metadata-path", type=Path, default=DEFAULT_METADATA_PATH)
    parser.add_argument(
        "--curated-viability-labels",
        type=Path,
        default=DEFAULT_CURATED_VIABILITY_PATH,
        help="CSV with human-reviewed pre-pit undercut_viable labels.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
