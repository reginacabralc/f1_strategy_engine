#!/usr/bin/env python
"""Build the Day 7 XGBoost lap-level pace dataset."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from pitwall.db.engine import create_db_engine
from pitwall.ingest.manifest import DEFAULT_MANIFEST_PATH, load_race_manifest
from pitwall.ml.dataset import build_dataset_from_db, write_dataset

DATASET_PATH = Path("data/ml/xgb_pace_dataset.parquet")
METADATA_PATH = Path("data/ml/xgb_pace_dataset.meta.json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--split-strategy",
        choices=("loro", "temporal_expanding", "temporal_year"),
        default=os.environ.get("SPLIT_STRATEGY", "temporal_expanding"),
    )
    parser.add_argument(
        "--target-strategy",
        choices=(
            "lap_time_delta",
            "session_normalized_delta",
            "stint_relative_delta",
            "absolute_lap_time",
            "season_circuit_compound_delta",
        ),
        default=os.environ.get("TARGET_STRATEGY", "session_normalized_delta"),
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--dataset-meta", type=Path, default=METADATA_PATH)
    parser.add_argument("--train-years", default=os.environ.get("TRAIN_YEARS", "2024"))
    parser.add_argument("--validation-years", default=os.environ.get("VALIDATION_YEARS", "2025"))
    parser.add_argument("--test-years", default=os.environ.get("TEST_YEARS", ""))
    parser.add_argument("--all-db-sessions", action="store_true")
    args = parser.parse_args()

    session_ids = _session_ids_from_manifest(args.manifest) if not args.all_db_sessions else ()
    engine = create_db_engine()
    with engine.begin() as connection:
        result = build_dataset_from_db(
            connection,
            session_ids=session_ids,
            split_strategy=args.split_strategy,
            train_years=_parse_years(args.train_years),
            validation_years=_parse_years(args.validation_years),
            test_years=_parse_years(args.test_years),
            target_strategy=args.target_strategy,
        )

    write_dataset(result, dataset_path=args.dataset, metadata_path=args.dataset_meta)

    print(f"Wrote {args.dataset}")
    print(f"Wrote {args.dataset_meta}")
    print(f"Rows: {result.metadata['row_count']}")
    print(f"Usable rows: {result.metadata['usable_row_count']}")
    print(f"Split strategy: {result.metadata['split_strategy']}")
    print(f"Target strategy: {result.metadata['target_strategy']}")
    print(f"Sessions: {', '.join(result.metadata['sessions_included'])}")
    print("Folds:")
    for fold in result.metadata["folds"]:
        evaluation = fold.get("validation_session_ids") or [fold.get("holdout_session_id")]
        print(f"  {fold['fold_id']}: eval={','.join(str(item) for item in evaluation)} "
              f"train={','.join(fold['train_session_ids'])}")
    return 0


def _session_ids_from_manifest(path: Path) -> tuple[str, ...]:
    if not path.exists():
        return ()
    manifest = load_race_manifest(path)
    return tuple(entry.session_id for entry in manifest.enabled_entries())


def _parse_years(value: str) -> tuple[int, ...]:
    if not value.strip():
        return ()
    return tuple(int(item.strip()) for item in value.split(",") if item.strip())


if __name__ == "__main__":
    raise SystemExit(main())
