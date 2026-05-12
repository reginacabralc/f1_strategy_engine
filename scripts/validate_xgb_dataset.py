#!/usr/bin/env python
"""Validate the generated Day 7 XGBoost pace dataset."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pitwall.degradation.dataset import DEMO_SESSION_IDS
from pitwall.ml.dataset import FEATURE_COLUMNS, TARGET_COLUMN, VALID_XGB_COMPOUNDS

DATASET_PATH = Path("data/ml/xgb_pace_dataset.parquet")
METADATA_PATH = Path("data/ml/xgb_pace_dataset.meta.json")


def main() -> int:
    errors = validate_dataset_files(DATASET_PATH, METADATA_PATH)
    if errors:
        print(f"FAILED: {len(errors)} validation error(s)")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("XGBoost dataset validation passed.")
    return 0


def validate_dataset_files(dataset_path: Path, metadata_path: Path) -> list[str]:
    errors: list[str] = []
    if not dataset_path.exists():
        return [f"dataset file missing: {dataset_path}"]
    if not metadata_path.exists():
        return [f"metadata file missing: {metadata_path}"]

    polars = __import__("polars")
    frame = polars.read_parquet(dataset_path)
    metadata = json.loads(metadata_path.read_text())

    if frame.height <= 0:
        errors.append("dataset row count is zero")
    if metadata.get("row_count") != frame.height:
        errors.append(
            f"metadata row_count={metadata.get('row_count')} does not match parquet rows={frame.height}"
        )

    required_columns = set(FEATURE_COLUMNS) | {
        TARGET_COLUMN,
        "fold_id",
        "split",
        "row_usable",
        "track_status",
        "is_pit_in_lap",
        "is_pit_out_lap",
        "is_deleted",
        "is_valid",
    }
    missing = sorted(required_columns - set(frame.columns))
    if missing:
        errors.append(f"missing required column(s): {missing}")

    pit_loss_columns = sorted(column for column in frame.columns if "pit_loss" in column)
    if pit_loss_columns:
        errors.append(f"pit-loss leakage column(s) found: {pit_loss_columns}")

    errors.extend(_validate_compounds(frame))
    errors.extend(_validate_clean_laps(frame))
    errors.extend(_validate_targets(frame))
    errors.extend(_validate_folds(frame, metadata))
    errors.extend(_validate_metadata(metadata))

    if not errors:
        _print_summary(frame, metadata)
    return errors


def _validate_compounds(frame: Any) -> list[str]:
    compounds = {str(value).upper() for value in frame["compound"].drop_nulls().unique()}
    unsupported = sorted(compounds - VALID_XGB_COMPOUNDS)
    return [f"unsupported compounds present: {unsupported}"] if unsupported else []


def _validate_clean_laps(frame: Any) -> list[str]:
    errors: list[str] = []
    polars = __import__("polars")
    if frame.filter(polars.col("is_pit_in_lap") | polars.col("is_pit_out_lap")).height:
        errors.append("pit-in or pit-out laps present")
    if frame.filter(polars.col("is_deleted") | ~polars.col("is_valid")).height:
        errors.append("invalid/deleted laps present")
    statuses = {str(value).upper() for value in frame["track_status"].drop_nulls().unique()}
    if statuses - {"GREEN"}:
        errors.append(f"non-green track status present: {sorted(statuses)}")
    return errors


def _validate_targets(frame: Any) -> list[str]:
    usable = frame.filter(frame["row_usable"])
    if usable.height and usable.filter(usable[TARGET_COLUMN].is_null()).height:
        return ["usable rows contain null target values"]
    return []


def _validate_folds(frame: Any, metadata: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_sessions = set(DEMO_SESSION_IDS)
    folds = metadata.get("folds", [])
    holdouts = {fold.get("holdout_session_id") for fold in folds}
    missing_holdouts = expected_sessions - holdouts
    if missing_holdouts:
        errors.append(f"missing LORO holdout fold(s): {sorted(missing_holdouts)}")

    polars = __import__("polars")
    for fold in folds:
        fold_id = fold.get("fold_id")
        holdout = fold.get("holdout_session_id")
        train_sessions = set(fold.get("train_session_ids", []))
        if holdout in train_sessions:
            errors.append(f"holdout leaked into train sessions for {fold_id}")
        fold_rows = frame.filter(polars.col("fold_id") == fold_id)
        holdout_rows = fold_rows.filter(polars.col("session_id") == holdout)
        if holdout_rows.height == 0:
            errors.append(f"fold {fold_id} has no holdout rows")
        bad_holdout_split = holdout_rows.filter(polars.col("split") != "holdout")
        if bad_holdout_split.height:
            errors.append(f"fold {fold_id} holdout rows not marked holdout")
        leaked_offset_rows = holdout_rows.filter(
            polars.col("driver_offset_source_sessions").str.contains(str(holdout), literal=True)
        )
        if leaked_offset_rows.height:
            errors.append(f"fold {fold_id} holdout driver offsets include holdout data")
        train_rows = fold_rows.filter(polars.col("session_id").is_in(list(train_sessions)))
        bad_train_split = train_rows.filter(polars.col("split") != "train")
        if bad_train_split.height:
            errors.append(f"fold {fold_id} train rows not marked train")
    return errors


def _validate_metadata(metadata: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    feature_columns = metadata.get("feature_columns", [])
    for column in FEATURE_COLUMNS:
        if column not in feature_columns:
            errors.append(f"metadata missing feature column {column}")
    if metadata.get("target_column") != TARGET_COLUMN:
        errors.append("metadata target column is not lap_time_delta_ms")
    leakage_text = " ".join(metadata.get("leakage_policy", [])).lower()
    if "pit loss excluded" not in leakage_text:
        errors.append("metadata does not document pit-loss exclusion")
    if "training sessions only" not in leakage_text:
        errors.append("metadata does not document fold-safe training-only leakage policy")
    return errors


def _print_summary(frame: Any, metadata: dict[str, Any]) -> None:
    print("XGBoost pace dataset")
    print(f"rows: {frame.height}")
    polars = __import__("polars")
    print(f"usable_rows: {frame.filter(polars.col('row_usable')).height}")
    print(f"sessions: {', '.join(metadata.get('sessions_included', []))}")
    print("folds:")
    for fold in metadata.get("folds", []):
        print(
            f"  {fold['fold_id']}: holdout={fold['holdout_session_id']} "
            f"train={','.join(fold['train_session_ids'])}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
