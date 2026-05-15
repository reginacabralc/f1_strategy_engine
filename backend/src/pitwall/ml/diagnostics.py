"""Diagnostics for temporal XGBoost target/reference shift."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
import polars as pl

from pitwall.ingest.normalize import to_bool, to_float
from pitwall.ml.dataset import TARGET_COLUMN, VALID_XGB_COMPOUNDS
from pitwall.ml.train import select_usable_rows, target_distribution

DEFAULT_SHIFT_REPORT_DIR = Path("reports/ml")


def build_shift_diagnostics(
    frame: pl.DataFrame,
    dataset_metadata: Mapping[str, Any],
    *,
    ingestion_report: Mapping[str, Any] | None = None,
    raw_rows: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build machine-readable diagnostics for target/reference shift."""

    usable = select_usable_rows(frame)
    rows = usable.to_dicts()
    folds = list(dataset_metadata.get("folds", []))
    ingestion = ingestion_report or {}
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "split_strategy": dataset_metadata.get("split_strategy"),
        "target_strategy": dataset_metadata.get("target_strategy", "lap_time_delta"),
        "row_count": int(frame.height),
        "usable_row_count": int(usable.height),
        "fold_target_summary": _fold_target_summary(rows, folds),
        "session_target_summary": _session_target_summary(rows),
        "reference_source_counts": _source_counts(rows, folds, "reference_source"),
        "driver_offset_source_counts": _source_counts(rows, folds, "driver_offset_source"),
        "reference_value_summary": _reference_value_summary(rows),
        "zero_usable_sessions": _zero_usable_sessions(
            dataset_metadata,
            ingestion_report=ingestion,
            raw_rows=raw_rows,
        ),
        "failed_ingestions": _failed_ingestions(ingestion),
        "extreme_fold_warnings": _extreme_fold_warnings(rows, folds),
    }


def write_shift_diagnostics(
    report: Mapping[str, Any],
    *,
    output_dir: Path = DEFAULT_SHIFT_REPORT_DIR,
) -> list[Path]:
    """Write JSON, CSV, and Markdown diagnostics under reports/ml."""

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "xgb_dataset_shift_report.json"
    markdown_path = output_dir / "xgb_dataset_shift_report.md"
    fold_csv = output_dir / "xgb_fold_target_summary.csv"
    session_csv = output_dir / "xgb_session_target_summary.csv"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    _write_csv(fold_csv, report.get("fold_target_summary", []))
    _write_csv(session_csv, report.get("session_target_summary", []))
    markdown_path.write_text(_markdown_summary(report))
    return [json_path, fold_csv, session_csv, markdown_path]


def _fold_target_summary(
    rows: Sequence[Mapping[str, Any]],
    folds: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    summaries = []
    rows_by_fold = _evaluation_rows_by_fold(rows, folds)
    for fold in folds:
        fold_id = str(fold.get("fold_id"))
        fold_rows = rows_by_fold.get(fold_id, [])
        if not fold_rows:
            continue
        values = np.array([float(row[TARGET_COLUMN]) for row in fold_rows], dtype=np.float64)
        summaries.append(
            {
                "fold_id": fold_id,
                "evaluation_sessions": ",".join(_evaluation_sessions(fold)),
                **target_distribution(values),
            }
        )
    return summaries


def _session_target_summary(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        if row.get("split") not in {"validation", "holdout", "test"}:
            continue
        grouped[(str(row.get("fold_id")), str(row.get("session_id")))].append(
            float(row[TARGET_COLUMN])
        )
    summaries = []
    for (fold_id, session_id), values in sorted(grouped.items()):
        target = np.array(values, dtype=np.float64)
        summaries.append(
            {
                "fold_id": fold_id,
                "session_id": session_id,
                **target_distribution(target),
            }
        )
    return summaries


def _source_counts(
    rows: Sequence[Mapping[str, Any]],
    folds: Sequence[Mapping[str, Any]],
    column: str,
) -> list[dict[str, Any]]:
    eval_rows_by_fold = _evaluation_rows_by_fold(rows, folds)
    output = []
    for fold_id, fold_rows in sorted(eval_rows_by_fold.items()):
        counts = Counter(str(row.get(column) or "UNKNOWN") for row in fold_rows)
        for source, count in sorted(counts.items()):
            output.append({"fold_id": fold_id, column: source, "rows": count})
    return output


def _reference_value_summary(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    values: dict[tuple[str, str, str, str], list[float]] = defaultdict(list)
    for row in rows:
        reference = to_float(row.get("reference_lap_time_ms"))
        if reference is None:
            continue
        key = (
            str(row.get("fold_id")),
            str(row.get("circuit_id")),
            str(row.get("compound")),
            str(row.get("reference_source")),
        )
        values[key].append(reference)
    output = []
    for (fold_id, circuit_id, compound, source), refs in sorted(values.items()):
        output.append(
            {
                "fold_id": fold_id,
                "circuit_id": circuit_id,
                "compound": compound,
                "reference_source": source,
                "median_reference_lap_time_ms": float(median(refs)),
                "rows": len(refs),
            }
        )
    return output


def _zero_usable_sessions(
    dataset_metadata: Mapping[str, Any],
    *,
    ingestion_report: Mapping[str, Any],
    raw_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    included = set(str(session_id) for session_id in dataset_metadata.get("sessions_included", []))
    raw_by_session: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in raw_rows:
        raw_by_session[str(row.get("session_id") or "")].append(row)
    output = []
    for item in ingestion_report.get("items", []):
        if item.get("status") != "succeeded":
            continue
        session_id = str(item.get("session_id") or "")
        if session_id in included:
            continue
        raw = raw_by_session.get(session_id, [])
        output.append(
            {
                "session_id": session_id,
                "year": item.get("year"),
                "round": item.get("round"),
                "label": item.get("label"),
                "dominant_reason": _dominant_zero_usable_reason(raw),
                "raw_rows": len(raw),
            }
        )
    return output


def _failed_ingestions(ingestion_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "session_id": item.get("session_id"),
            "year": item.get("year"),
            "round": item.get("round"),
            "label": item.get("label"),
            "error": item.get("error"),
        }
        for item in ingestion_report.get("items", [])
        if item.get("status") == "failed"
    ]


def _extreme_fold_warnings(
    rows: Sequence[Mapping[str, Any]],
    folds: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    warnings = []
    for summary in _fold_target_summary(rows, folds):
        mean_ms = float(summary["mean_ms"])
        if abs(mean_ms) >= 5_000:
            warnings.append(
                {
                    "fold_id": summary["fold_id"],
                    "mean_ms": mean_ms,
                    "reason": "absolute target mean exceeds 5000 ms",
                }
            )
    return warnings


def _dominant_zero_usable_reason(rows: Sequence[Mapping[str, Any]]) -> str:
    if not rows:
        return "no_raw_rows_loaded"
    compounds = {str(row.get("compound") or "").upper() for row in rows}
    if not compounds <= VALID_XGB_COMPOUNDS:
        return "unsupported_or_missing_compound"
    if any(str(row.get("track_status") or "GREEN").upper() != "GREEN" for row in rows):
        return "non_green_or_mixed_conditions"
    if any(to_bool(row.get("is_pit_in_lap")) or to_bool(row.get("is_pit_out_lap")) for row in rows):
        return "pit_laps_only"
    return "filtered_by_clean_lap_rules"


def _evaluation_rows_by_fold(
    rows: Sequence[Mapping[str, Any]],
    folds: Sequence[Mapping[str, Any]],
) -> dict[str, list[Mapping[str, Any]]]:
    output: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    split_by_fold = {str(fold.get("fold_id")): _evaluation_split(fold) for fold in folds}
    for row in rows:
        fold_id = str(row.get("fold_id"))
        if row.get("split") == split_by_fold.get(fold_id):
            output[fold_id].append(row)
    return output


def _evaluation_split(fold: Mapping[str, Any]) -> str:
    if fold.get("validation_session_ids"):
        return "validation"
    if fold.get("test_session_ids"):
        return "test"
    return "holdout"


def _evaluation_sessions(fold: Mapping[str, Any]) -> list[str]:
    return [
        str(session_id)
        for session_id in (
            fold.get("validation_session_ids")
            or fold.get("test_session_ids")
            or ([fold.get("holdout_session_id")] if fold.get("holdout_session_id") else [])
        )
    ]


def _write_csv(path: Path, rows: object) -> None:
    if not isinstance(rows, list) or not rows:
        path.write_text("")
        return
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _markdown_summary(report: Mapping[str, Any]) -> str:
    lines = [
        "# XGBoost Dataset Shift Report",
        "",
        f"- split_strategy: `{report.get('split_strategy')}`",
        f"- target_strategy: `{report.get('target_strategy')}`",
        f"- rows: `{report.get('row_count')}`",
        f"- usable rows: `{report.get('usable_row_count')}`",
        "",
        "## Extreme Fold Warnings",
    ]
    warnings = report.get("extreme_fold_warnings", [])
    if isinstance(warnings, list) and warnings:
        lines.extend(f"- `{row['fold_id']}` mean `{row['mean_ms']:.1f}` ms" for row in warnings)
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Zero-Usable Sessions")
    zero_usable = report.get("zero_usable_sessions", [])
    if isinstance(zero_usable, list) and zero_usable:
        lines.extend(
            f"- `{row['session_id']}`: {row['dominant_reason']} ({row['raw_rows']} raw rows)"
            for row in zero_usable
        )
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"
