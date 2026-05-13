#!/usr/bin/env python
"""Diagnose temporal target/reference shift in the XGBoost pace dataset."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from pitwall.db.engine import create_db_engine
from pitwall.ml.dataset import load_clean_pace_laps
from pitwall.ml.diagnostics import (
    DEFAULT_SHIFT_REPORT_DIR,
    build_shift_diagnostics,
    write_shift_diagnostics,
)
from pitwall.ml.train import DEFAULT_DATASET_METADATA_PATH, DEFAULT_DATASET_PATH, load_dataset

INGESTION_REPORT_PATH = Path("data/ml/ingestion_report.json")

logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--dataset-meta", type=Path, default=DEFAULT_DATASET_METADATA_PATH)
    parser.add_argument("--ingestion-report", type=Path, default=INGESTION_REPORT_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_SHIFT_REPORT_DIR)
    parser.add_argument("--skip-db-inspection", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    frame, metadata = load_dataset(args.dataset, args.dataset_meta)
    ingestion_report = _load_json(args.ingestion_report)
    raw_rows = [] if args.skip_db_inspection else _load_raw_rows(ingestion_report)
    report = build_shift_diagnostics(
        frame,
        metadata,
        ingestion_report=ingestion_report,
        raw_rows=raw_rows,
    )
    paths = write_shift_diagnostics(report, output_dir=args.output_dir)

    logger.info("wrote %d shift diagnostic artifacts to %s", len(paths), args.output_dir)
    for warning in report["extreme_fold_warnings"]:
        logger.warning(
            "extreme target shift: %s mean=%.1f ms",
            warning["fold_id"],
            warning["mean_ms"],
        )
    for session in report["zero_usable_sessions"]:
        logger.warning(
            "zero usable session: %s reason=%s",
            session["session_id"],
            session["dominant_reason"],
        )
    for failure in report["failed_ingestions"]:
        logger.warning("failed ingestion: %s error=%s", failure["session_id"], failure["error"])
    for path in paths:
        print(path)
    return 0


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _load_raw_rows(ingestion_report: dict) -> list[dict]:
    session_ids = tuple(
        str(item.get("session_id"))
        for item in ingestion_report.get("items", [])
        if item.get("session_id") and item.get("status") == "succeeded"
    )
    if not session_ids:
        return []
    engine = create_db_engine()
    with engine.begin() as connection:
        return load_clean_pace_laps(connection, session_ids=session_ids)


if __name__ == "__main__":
    raise SystemExit(main())

