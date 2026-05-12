"""Build leakage-safe lap-level datasets for XGBoost pace training."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from statistics import median
from typing import Any, Protocol

from pitwall.degradation.dataset import DEMO_SESSION_IDS, refresh_clean_air_lap_times
from pitwall.ingest.normalize import clean_nulls, to_bool, to_float, to_int

VALID_XGB_COMPOUNDS = frozenset({"SOFT", "MEDIUM", "HARD"})
TARGET_COLUMN = "lap_time_delta_ms"
FEATURE_COLUMNS = [
    "session_id",
    "circuit_id",
    "driver_code",
    "team_code",
    "compound",
    "tyre_age",
    "lap_number",
    "stint_number",
    "lap_in_stint",
    "lap_in_stint_ratio",
    "race_progress",
    "fuel_proxy",
    "track_temp_c",
    "air_temp_c",
    "position",
    "gap_to_ahead_ms",
    "gap_to_leader_ms",
    "is_in_traffic",
    "dirty_air_proxy_ms",
    "driver_pace_offset_ms",
    "driver_pace_offset_missing",
    "reference_lap_time_ms",
]

DATASET_COLUMNS = [
    *FEATURE_COLUMNS,
    TARGET_COLUMN,
    "fold_id",
    "split",
    "row_usable",
    "missing_reason",
    "reference_source",
    "driver_offset_source",
    "driver_offset_source_sessions",
    "track_status",
    "is_pit_in_lap",
    "is_pit_out_lap",
    "is_deleted",
    "is_valid",
]

PACE_LAP_QUERY = """
    WITH weather_by_lap AS (
        SELECT
            session_id,
            lap_number,
            AVG(track_temp_c)::DOUBLE PRECISION AS track_temp_c,
            AVG(air_temp_c)::DOUBLE PRECISION AS air_temp_c
        FROM weather
        GROUP BY session_id, lap_number
    )
    SELECT
        l.session_id,
        e.circuit_id,
        l.driver_code,
        d.team_code,
        l.compound,
        l.tyre_age,
        l.lap_number,
        st.stint_number,
        l.lap_time_ms,
        l.track_status,
        l.is_pit_in AS is_pit_in_lap,
        l.is_pit_out AS is_pit_out_lap,
        NOT l.is_valid AS is_deleted,
        l.is_valid,
        s.total_laps,
        l.position,
        l.gap_to_ahead_ms,
        l.gap_to_leader_ms,
        w.track_temp_c,
        w.air_temp_c,
        CASE
            WHEN st.lap_start IS NULL THEN NULL
            ELSE GREATEST(1, l.lap_number - st.lap_start + 1)
        END AS lap_in_stint,
        CASE
            WHEN st.lap_start IS NULL OR st.lap_end IS NULL OR st.lap_end < st.lap_start
                THEN NULL
            ELSE (
                GREATEST(1, l.lap_number - st.lap_start + 1)::DOUBLE PRECISION
                / GREATEST(1, st.lap_end - st.lap_start + 1)
            )
        END AS lap_in_stint_ratio
    FROM laps l
    JOIN sessions s ON s.session_id = l.session_id
    JOIN events e ON e.event_id = s.event_id
    LEFT JOIN drivers d ON d.driver_code = l.driver_code
    LEFT JOIN stints st
      ON st.session_id = l.session_id
     AND st.driver_code = l.driver_code
     AND l.lap_number BETWEEN st.lap_start AND COALESCE(st.lap_end, l.lap_number)
    LEFT JOIN weather_by_lap w
      ON w.session_id = l.session_id
     AND w.lap_number = l.lap_number
    WHERE (:session_ids_is_null OR l.session_id = ANY(:session_ids))
    ORDER BY l.session_id, l.driver_code, l.lap_number
"""


class QueryConnection(Protocol):
    def execute(self, statement: Any, parameters: Mapping[str, object] | None = None) -> Any: ...


@dataclass(frozen=True, slots=True)
class FoldSpec:
    fold_id: str
    holdout_session_id: str
    train_session_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReferencePace:
    by_circuit_compound: dict[tuple[str, str], float]
    by_compound: dict[str, float]


@dataclass(frozen=True, slots=True)
class DriverOffsetLookup:
    exact: dict[tuple[str, str, str], float]
    by_driver_compound: dict[tuple[str, str], float]
    source_sessions: str


@dataclass(frozen=True, slots=True)
class DatasetBuildResult:
    rows: list[dict[str, Any]]
    metadata: dict[str, Any]


def load_clean_pace_laps(
    connection: QueryConnection,
    *,
    session_ids: tuple[str, ...] = DEMO_SESSION_IDS,
) -> list[dict[str, Any]]:
    """Load raw lap rows used by the Day 7 pace dataset builder."""

    params: dict[str, object] = {
        "session_ids": list(session_ids),
        "session_ids_is_null": not session_ids,
    }
    rows = connection.execute(_sql_text(PACE_LAP_QUERY), params)
    return [dict(row._mapping) for row in rows]


def build_loro_dataset(
    rows: Iterable[Mapping[str, Any]],
    *,
    generated_at: datetime | None = None,
) -> DatasetBuildResult:
    """Build one train/holdout copy of every clean lap for each LORO fold."""

    clean_rows = [_normalise_lap(row) for row in rows]
    eligible_rows = [row for row in clean_rows if _is_training_eligible(row)]
    session_ids = sorted({str(row["session_id"]) for row in eligible_rows})
    folds = build_loro_folds(session_ids)

    dataset_rows: list[dict[str, Any]] = []
    for fold in folds:
        train_rows = [
            row for row in eligible_rows if str(row["session_id"]) in fold.train_session_ids
        ]
        references = compute_reference_pace(train_rows)
        driver_offsets = compute_driver_offsets_for_fold(train_rows, references, fold)
        for row in eligible_rows:
            dataset_rows.append(_build_dataset_row(row, fold, references, driver_offsets))

    timestamp = generated_at or datetime.now(UTC)
    metadata = _build_metadata(dataset_rows, folds, session_ids, timestamp)
    return DatasetBuildResult(rows=dataset_rows, metadata=metadata)


def build_loro_folds(session_ids: Iterable[str]) -> list[FoldSpec]:
    """Return deterministic leave-one-race-out folds keyed by session_id."""

    sessions = tuple(sorted({session_id for session_id in session_ids if session_id}))
    return [
        FoldSpec(
            fold_id=f"fold_{holdout_session_id}",
            holdout_session_id=holdout_session_id,
            train_session_ids=tuple(s for s in sessions if s != holdout_session_id),
        )
        for holdout_session_id in sessions
    ]


def compute_reference_pace(rows: Iterable[Mapping[str, Any]]) -> ReferencePace:
    """Compute fold-local median reference pace maps."""

    by_circuit_compound_values: dict[tuple[str, str], list[float]] = defaultdict(list)
    by_compound_values: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        circuit_id = str(row.get("circuit_id") or "")
        compound = str(row.get("compound") or "").upper()
        lap_time_ms = to_float(row.get("lap_time_ms"))
        if not circuit_id or compound not in VALID_XGB_COMPOUNDS or lap_time_ms is None:
            continue
        by_circuit_compound_values[(circuit_id, compound)].append(lap_time_ms)
        by_compound_values[compound].append(lap_time_ms)
    return ReferencePace(
        by_circuit_compound={
            group: float(median(values))
            for group, values in by_circuit_compound_values.items()
            if values
        },
        by_compound={
            compound: float(median(values))
            for compound, values in by_compound_values.items()
            if values
        },
    )


def compute_driver_offsets_for_fold(
    train_rows: Iterable[Mapping[str, Any]],
    references: ReferencePace,
    fold: FoldSpec,
) -> DriverOffsetLookup:
    """Compute fold-safe driver offsets using training sessions only."""

    residuals_exact: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    residuals_driver_compound: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in train_rows:
        reference, _source = _reference_for_row(row, references)
        lap_time_ms = to_float(row.get("lap_time_ms"))
        if reference is None or lap_time_ms is None:
            continue
        driver_code = str(row.get("driver_code") or "")
        circuit_id = str(row.get("circuit_id") or "")
        compound = str(row.get("compound") or "").upper()
        if not driver_code or not circuit_id or compound not in VALID_XGB_COMPOUNDS:
            continue
        residual = lap_time_ms - reference
        residuals_exact[(driver_code, circuit_id, compound)].append(residual)
        residuals_driver_compound[(driver_code, compound)].append(residual)
    return DriverOffsetLookup(
        exact={key: float(median(values)) for key, values in residuals_exact.items()},
        by_driver_compound={
            key: float(median(values)) for key, values in residuals_driver_compound.items()
        },
        source_sessions=",".join(fold.train_session_ids),
    )


def validate_dataset_rows(rows: Sequence[Mapping[str, Any]], metadata: Mapping[str, Any]) -> None:
    """Validate in-memory dataset rows before writing or training."""

    if not rows:
        raise ValueError("XGBoost dataset has zero rows")
    columns = set().union(*(row.keys() for row in rows))
    pit_loss_columns = sorted(column for column in columns if "pit_loss" in column)
    if pit_loss_columns:
        raise ValueError(f"pit_loss leakage columns are not allowed: {pit_loss_columns}")
    required = [*FEATURE_COLUMNS, TARGET_COLUMN, "fold_id", "split"]
    missing = [column for column in required if column not in columns]
    if missing:
        raise ValueError(f"missing required XGBoost dataset column(s): {missing}")
    compounds = {str(row.get("compound") or "").upper() for row in rows}
    unsupported = sorted(compounds - VALID_XGB_COMPOUNDS)
    if unsupported:
        raise ValueError(f"unsupported compound(s) in XGBoost dataset: {unsupported}")

    for row in rows:
        if to_bool(row.get("row_usable")) and row.get(TARGET_COLUMN) is None:
            raise ValueError("usable row has NULL lap_time_delta_ms")
        if to_bool(row.get("is_pit_in_lap")) or to_bool(row.get("is_pit_out_lap")):
            raise ValueError("pit-in/out lap leaked into XGBoost dataset")
        if to_bool(row.get("is_deleted")) or row.get("is_valid") is False:
            raise ValueError("invalid/deleted lap leaked into XGBoost dataset")
        track_status = str(row.get("track_status") or "GREEN").upper()
        if track_status != "GREEN":
            raise ValueError("non-green lap leaked into XGBoost dataset")

    for fold in metadata.get("folds", []):
        holdout = fold.get("holdout_session_id")
        train_sessions = set(fold.get("train_session_ids", []))
        if holdout in train_sessions:
            raise ValueError(f"holdout session leaked into train sessions for {fold}")


def write_dataset(
    result: DatasetBuildResult,
    *,
    dataset_path: Path,
    metadata_path: Path,
) -> None:
    """Write dataset parquet and metadata JSON artifacts."""

    validate_dataset_rows(result.rows, result.metadata)
    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    polars = import_module("polars")
    polars.DataFrame(result.rows, schema=DATASET_COLUMNS).write_parquet(dataset_path)
    metadata_path.write_text(json.dumps(result.metadata, indent=2, sort_keys=True) + "\n")


def build_dataset_from_db(
    connection: QueryConnection,
    *,
    session_ids: tuple[str, ...] = DEMO_SESSION_IDS,
) -> DatasetBuildResult:
    """Refresh clean-air diagnostics, load DB laps, and build the dataset."""

    refresh_clean_air_lap_times(connection)
    return build_loro_dataset(load_clean_pace_laps(connection, session_ids=session_ids))


def _build_dataset_row(
    row: Mapping[str, Any],
    fold: FoldSpec,
    references: ReferencePace,
    driver_offsets: DriverOffsetLookup,
) -> dict[str, Any]:
    reference, reference_source = _reference_for_row(row, references)
    lap_time_ms = to_float(row.get("lap_time_ms"))
    target = (
        lap_time_ms - reference
        if lap_time_ms is not None and reference is not None
        else None
    )
    driver_offset, missing, driver_source = _driver_offset_for_row(row, driver_offsets)

    lap_number = to_int(row.get("lap_number"))
    total_laps = to_int(row.get("total_laps"))
    race_progress = (
        max(0.0, min(1.0, lap_number / total_laps))
        if lap_number is not None and total_laps is not None and total_laps > 0
        else None
    )
    gap_to_ahead_ms = to_int(row.get("gap_to_ahead_ms"))

    return {
        "session_id": row.get("session_id"),
        "circuit_id": row.get("circuit_id"),
        "driver_code": row.get("driver_code"),
        "team_code": row.get("team_code"),
        "compound": row.get("compound"),
        "tyre_age": to_int(row.get("tyre_age")),
        "lap_number": lap_number,
        "stint_number": to_int(row.get("stint_number")),
        "lap_in_stint": to_int(row.get("lap_in_stint")),
        "lap_in_stint_ratio": to_float(row.get("lap_in_stint_ratio")),
        "race_progress": race_progress,
        "fuel_proxy": (1.0 - race_progress) if race_progress is not None else None,
        "track_temp_c": to_float(row.get("track_temp_c")),
        "air_temp_c": to_float(row.get("air_temp_c")),
        "position": to_int(row.get("position")),
        "gap_to_ahead_ms": gap_to_ahead_ms,
        "gap_to_leader_ms": to_int(row.get("gap_to_leader_ms")),
        "is_in_traffic": gap_to_ahead_ms is not None and gap_to_ahead_ms < 1500,
        "dirty_air_proxy_ms": max(0, 2000 - gap_to_ahead_ms)
        if gap_to_ahead_ms is not None
        else 0,
        "driver_pace_offset_ms": driver_offset,
        "driver_pace_offset_missing": missing,
        "reference_lap_time_ms": reference,
        TARGET_COLUMN: target,
        "fold_id": fold.fold_id,
        "split": "holdout" if row.get("session_id") == fold.holdout_session_id else "train",
        "row_usable": target is not None,
        "missing_reason": None if target is not None else "missing_reference",
        "reference_source": reference_source,
        "driver_offset_source": driver_source,
        "driver_offset_source_sessions": driver_offsets.source_sessions,
        "track_status": row.get("track_status"),
        "is_pit_in_lap": to_bool(row.get("is_pit_in_lap")),
        "is_pit_out_lap": to_bool(row.get("is_pit_out_lap")),
        "is_deleted": to_bool(row.get("is_deleted")),
        "is_valid": to_bool(row.get("is_valid")),
    }


def _reference_for_row(
    row: Mapping[str, Any],
    references: ReferencePace,
) -> tuple[float | None, str]:
    circuit_id = str(row.get("circuit_id") or "")
    compound = str(row.get("compound") or "").upper()
    if (circuit_id, compound) in references.by_circuit_compound:
        return references.by_circuit_compound[(circuit_id, compound)], "circuit_compound"
    if compound in references.by_compound:
        return references.by_compound[compound], "global_compound"
    return None, "missing_reference"


def _driver_offset_for_row(
    row: Mapping[str, Any],
    offsets: DriverOffsetLookup,
) -> tuple[float, bool, str]:
    driver_code = str(row.get("driver_code") or "")
    circuit_id = str(row.get("circuit_id") or "")
    compound = str(row.get("compound") or "").upper()
    exact_key = (driver_code, circuit_id, compound)
    fallback_key = (driver_code, compound)
    if exact_key in offsets.exact:
        return offsets.exact[exact_key], False, "driver_circuit_compound"
    if fallback_key in offsets.by_driver_compound:
        return offsets.by_driver_compound[fallback_key], False, "driver_compound"
    return 0.0, True, "missing_default_zero"


def _normalise_lap(row: Mapping[str, Any]) -> dict[str, Any]:
    record = dict(clean_nulls(dict(row)))
    record["compound"] = str(record.get("compound") or "").upper()
    record["track_status"] = str(record.get("track_status") or "GREEN").upper()
    record["is_pit_in_lap"] = to_bool(record.get("is_pit_in_lap"))
    record["is_pit_out_lap"] = to_bool(record.get("is_pit_out_lap"))
    record["is_deleted"] = to_bool(record.get("is_deleted"))
    record["is_valid"] = to_bool(record.get("is_valid", True))
    return record


def _is_training_eligible(row: Mapping[str, Any]) -> bool:
    if to_int(row.get("lap_time_ms")) is None:
        return False
    if str(row.get("compound") or "").upper() not in VALID_XGB_COMPOUNDS:
        return False
    if to_int(row.get("tyre_age")) is None:
        return False
    if to_bool(row.get("is_pit_in_lap")) or to_bool(row.get("is_pit_out_lap")):
        return False
    if to_bool(row.get("is_deleted")) or row.get("is_valid") is False:
        return False
    return str(row.get("track_status") or "GREEN").upper() == "GREEN"


def _build_metadata(
    rows: Sequence[Mapping[str, Any]],
    folds: list[FoldSpec],
    session_ids: list[str],
    generated_at: datetime,
) -> dict[str, Any]:
    usable_rows = [row for row in rows if row.get("row_usable") is True]
    return {
        "row_count": len(rows),
        "usable_row_count": len(usable_rows),
        "feature_columns": FEATURE_COLUMNS,
        "target_column": TARGET_COLUMN,
        "sessions_included": session_ids,
        "folds": [
            {
                "fold_id": fold.fold_id,
                "holdout_session_id": fold.holdout_session_id,
                "train_session_ids": list(fold.train_session_ids),
            }
            for fold in folds
        ],
        "reference_pace_method": (
            "median clean lap time from fold training sessions; "
            "fallback circuit+compound -> global compound -> missing_reference"
        ),
        "driver_offset_method": (
            "median driver residual from fold training sessions only; "
            "fallback driver+circuit+compound -> driver+compound -> 0 with missing flag"
        ),
        "filtering_rules": [
            "green track status only",
            "dry compounds only: SOFT, MEDIUM, HARD",
            "exclude pit-in and pit-out laps",
            "exclude invalid/deleted laps",
            "require lap_time_ms and tyre_age",
        ],
        "leakage_policy": [
            "leave-one-race-out by session_id",
            "holdout reference pace uses training sessions only",
            "holdout driver offsets use training sessions only",
            "pit loss excluded from lap-level pace dataset",
        ],
        "generated_at": generated_at.isoformat(),
        "known_limitations": [
            "three demo races only",
            "traffic represented by simple gap proxies",
            "categorical encoding deferred to Day 8 training",
            "no pit-loss or pair-level undercut outcome features in this dataset",
        ],
    }


def _sql_text(sql: str) -> Any:
    sqlalchemy = import_module("sqlalchemy")
    return sqlalchemy.text(sql)
