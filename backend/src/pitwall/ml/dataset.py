"""Build leakage-safe lap-level datasets for XGBoost pace training."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import import_module
from math import ceil
from pathlib import Path
from statistics import median
from typing import Any, Protocol

from pitwall.degradation.dataset import DEMO_SESSION_IDS, refresh_clean_air_lap_times
from pitwall.ingest.normalize import clean_nulls, to_bool, to_float, to_int

VALID_XGB_COMPOUNDS = frozenset({"SOFT", "MEDIUM", "HARD"})
VALID_TARGET_STRATEGIES = frozenset(
    {
        "lap_time_delta",
        "session_normalized_delta",
        "stint_relative_delta",
        "absolute_lap_time",
        "season_circuit_compound_delta",
    }
)
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
    "season",
    "round_number",
    "event_order",
    "split_strategy",
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
        e.season,
        e.round_number,
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
    train_session_ids: tuple[str, ...]
    holdout_session_id: str | None = None
    validation_session_ids: tuple[str, ...] = ()
    test_session_ids: tuple[str, ...] = ()
    train_event_orders: tuple[int, ...] = ()
    validation_event_orders: tuple[int, ...] = ()
    test_event_orders: tuple[int, ...] = ()

    @property
    def evaluation_session_ids(self) -> tuple[str, ...]:
        if self.validation_session_ids:
            return self.validation_session_ids
        if self.holdout_session_id:
            return (self.holdout_session_id,)
        return self.test_session_ids

    @property
    def evaluation_split_name(self) -> str:
        if self.validation_session_ids:
            return "validation"
        if self.holdout_session_id:
            return "holdout"
        return "test"


@dataclass(frozen=True, slots=True)
class SessionOrder:
    session_id: str
    season: int
    round_number: int
    event_order: int


@dataclass(frozen=True, slots=True)
class ReferencePace:
    by_season_circuit_compound: dict[tuple[int, str, str], float]
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
    target_strategy: str = "lap_time_delta",
    generated_at: datetime | None = None,
) -> DatasetBuildResult:
    """Build one train/holdout copy of every clean lap for each LORO fold."""

    _validate_target_strategy(target_strategy)
    clean_rows = [_normalise_lap(row) for row in rows]
    eligible_rows = [row for row in clean_rows if _is_training_eligible(row)]
    session_ids = sorted({str(row["session_id"]) for row in eligible_rows})
    folds = build_loro_folds(session_ids)

    dataset_rows = _build_rows_for_folds(
        eligible_rows,
        folds,
        split_strategy="loro",
        session_orders=_infer_session_orders(eligible_rows),
        target_strategy=target_strategy,
    )

    timestamp = generated_at or datetime.now(UTC)
    metadata = _build_metadata(
        dataset_rows,
        folds,
        session_ids,
        timestamp,
        split_strategy="loro",
        session_orders=_infer_session_orders(eligible_rows),
        final_test_status="not_configured",
        target_strategy=target_strategy,
    )
    return DatasetBuildResult(rows=dataset_rows, metadata=metadata)


def build_loro_folds(session_ids: Iterable[str]) -> list[FoldSpec]:
    """Return deterministic leave-one-race-out folds keyed by session_id."""

    sessions = tuple(sorted({session_id for session_id in session_ids if session_id}))
    return [
        FoldSpec(
            fold_id=f"fold_{holdout_session_id}",
            train_session_ids=tuple(s for s in sessions if s != holdout_session_id),
            holdout_session_id=holdout_session_id,
        )
        for holdout_session_id in sessions
    ]


def build_temporal_expanding_dataset(
    rows: Iterable[Mapping[str, Any]],
    *,
    block_size: int | None = None,
    target_strategy: str = "lap_time_delta",
    generated_at: datetime | None = None,
) -> DatasetBuildResult:
    """Build expanding-window folds ordered by season and round."""

    _validate_target_strategy(target_strategy)
    clean_rows = [_normalise_lap(row) for row in rows]
    eligible_rows = [row for row in clean_rows if _is_training_eligible(row)]
    session_orders = _infer_session_orders(eligible_rows)
    folds = build_temporal_expanding_folds(
        [(row.session_id, row.season, row.round_number) for row in session_orders],
        block_size=block_size,
    )
    dataset_rows = _build_rows_for_folds(
        eligible_rows,
        folds,
        split_strategy="temporal_expanding",
        session_orders=session_orders,
        target_strategy=target_strategy,
    )
    timestamp = generated_at or datetime.now(UTC)
    metadata = _build_metadata(
        dataset_rows,
        folds,
        [row.session_id for row in session_orders],
        timestamp,
        split_strategy="temporal_expanding",
        session_orders=session_orders,
        final_test_status="not_configured",
        target_strategy=target_strategy,
    )
    return DatasetBuildResult(rows=dataset_rows, metadata=metadata)


def build_temporal_expanding_folds(
    sessions: Iterable[tuple[str, int, int]],
    *,
    block_size: int | None = None,
) -> list[FoldSpec]:
    """Return expanding-window folds over chronological session order."""

    ordered = _session_orders_from_tuples(sessions)
    if len(ordered) < 2:
        return []
    window = block_size or _default_temporal_block_size(ordered)
    if window <= 0:
        raise ValueError("temporal block_size must be positive")

    folds: list[FoldSpec] = []
    validation_start = window
    fold_number = 1
    while validation_start < len(ordered):
        validation_end = min(validation_start + window, len(ordered))
        train = ordered[:validation_start]
        validation = ordered[validation_start:validation_end]
        if train and validation:
            folds.append(
                FoldSpec(
                    fold_id=f"fold_{fold_number:03d}",
                    train_session_ids=tuple(row.session_id for row in train),
                    validation_session_ids=tuple(row.session_id for row in validation),
                    train_event_orders=tuple(row.event_order for row in train),
                    validation_event_orders=tuple(row.event_order for row in validation),
                )
            )
            fold_number += 1
        validation_start = validation_end
    return folds


def build_temporal_year_dataset(
    rows: Iterable[Mapping[str, Any]],
    *,
    train_years: tuple[int, ...],
    validation_years: tuple[int, ...],
    test_years: tuple[int, ...] = (),
    target_strategy: str = "lap_time_delta",
    generated_at: datetime | None = None,
) -> DatasetBuildResult:
    """Build one explicit temporal-year split."""

    _validate_target_strategy(target_strategy)
    clean_rows = [_normalise_lap(row) for row in rows]
    eligible_rows = [row for row in clean_rows if _is_training_eligible(row)]
    session_orders = _infer_session_orders(eligible_rows)
    by_year = {row.session_id: row.season for row in session_orders}
    train_sessions = tuple(row.session_id for row in session_orders if row.season in train_years)
    validation_sessions = tuple(
        row.session_id for row in session_orders if row.season in validation_years
    )
    test_sessions = tuple(row.session_id for row in session_orders if row.season in test_years)
    if not train_sessions or not validation_sessions:
        raise ValueError("temporal_year requires at least one train and validation session")
    if max(train_years) >= min(validation_years):
        raise ValueError("temporal_year train years must be before validation years")
    if test_years and max(validation_years) >= min(test_years):
        raise ValueError("temporal_year validation years must be before test years")

    fold = FoldSpec(
        fold_id="fold_temporal_year",
        train_session_ids=train_sessions,
        validation_session_ids=validation_sessions,
        test_session_ids=test_sessions,
        train_event_orders=tuple(
            row.event_order for row in session_orders if row.session_id in train_sessions
        ),
        validation_event_orders=tuple(
            row.event_order for row in session_orders if row.session_id in validation_sessions
        ),
        test_event_orders=tuple(
            row.event_order for row in session_orders if row.session_id in test_sessions
        ),
    )
    dataset_rows = _build_rows_for_folds(
        eligible_rows,
        [fold],
        split_strategy="temporal_year",
        session_orders=session_orders,
        target_strategy=target_strategy,
    )
    timestamp = generated_at or datetime.now(UTC)
    included_years = {*train_years, *validation_years, *test_years}
    metadata = _build_metadata(
        dataset_rows,
        [fold],
        [row.session_id for row in session_orders if by_year[row.session_id] in included_years],
        timestamp,
        split_strategy="temporal_year",
        session_orders=session_orders,
        final_test_status="reserved" if test_sessions else "not_configured",
        target_strategy=target_strategy,
    )
    metadata["train_years"] = list(train_years)
    metadata["validation_years"] = list(validation_years)
    metadata["test_years"] = list(test_years)
    return DatasetBuildResult(rows=dataset_rows, metadata=metadata)


def compute_reference_pace(rows: Iterable[Mapping[str, Any]]) -> ReferencePace:
    """Compute fold-local median reference pace maps."""

    by_season_circuit_compound_values: dict[tuple[int, str, str], list[float]] = defaultdict(list)
    by_circuit_compound_values: dict[tuple[str, str], list[float]] = defaultdict(list)
    by_compound_values: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        season = to_int(row.get("season"))
        circuit_id = str(row.get("circuit_id") or "")
        compound = str(row.get("compound") or "").upper()
        lap_time_ms = to_float(row.get("lap_time_ms"))
        if not circuit_id or compound not in VALID_XGB_COMPOUNDS or lap_time_ms is None:
            continue
        if season is not None:
            by_season_circuit_compound_values[(season, circuit_id, compound)].append(lap_time_ms)
        by_circuit_compound_values[(circuit_id, compound)].append(lap_time_ms)
        by_compound_values[compound].append(lap_time_ms)
    return ReferencePace(
        by_season_circuit_compound={
            group: float(median(values))
            for group, values in by_season_circuit_compound_values.items()
            if values
        },
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


def _build_rows_for_folds(
    eligible_rows: Sequence[Mapping[str, Any]],
    folds: Sequence[FoldSpec],
    *,
    split_strategy: str,
    session_orders: Sequence[SessionOrder],
    target_strategy: str,
) -> list[dict[str, Any]]:
    event_order_by_session = {row.session_id: row.event_order for row in session_orders}
    past_refs = _compute_past_references(eligible_rows)
    dataset_rows: list[dict[str, Any]] = []
    for fold in folds:
        train_session_set = set(fold.train_session_ids)
        validation_session_set = set(fold.validation_session_ids)
        test_session_set = set(fold.test_session_ids)
        holdout_session_set = {fold.holdout_session_id} if fold.holdout_session_id else set()
        included_sessions = (
            train_session_set | validation_session_set | test_session_set | holdout_session_set
        )
        train_rows = [row for row in eligible_rows if str(row["session_id"]) in train_session_set]
        references = compute_reference_pace(train_rows)
        driver_offsets = compute_driver_offsets_for_fold(train_rows, references, fold)
        for row in eligible_rows:
            session_id = str(row.get("session_id") or "")
            if included_sessions and session_id not in included_sessions:
                continue
            if session_id in train_session_set:
                split = "train"
            elif session_id in validation_session_set:
                split = "validation"
            elif session_id in test_session_set:
                split = "test"
            elif session_id in holdout_session_set:
                split = "holdout"
            else:
                continue
            dataset_rows.append(
                _build_dataset_row(
                    row,
                    fold,
                    references,
                    driver_offsets,
                    split=split,
                    split_strategy=split_strategy,
                    event_order=event_order_by_session.get(session_id),
                    target_strategy=target_strategy,
                    past_references=past_refs,
                )
            )
    return dataset_rows


def validate_dataset_rows(rows: Sequence[Mapping[str, Any]], metadata: Mapping[str, Any]) -> None:
    """Validate in-memory dataset rows before writing or training."""

    if not rows:
        raise ValueError("XGBoost dataset has zero rows")
    columns = set().union(*(row.keys() for row in rows))
    pit_loss_columns = sorted(column for column in columns if "pit_loss" in column)
    if pit_loss_columns:
        raise ValueError(f"pit_loss leakage columns are not allowed: {pit_loss_columns}")
    required = [
        *FEATURE_COLUMNS,
        TARGET_COLUMN,
        "fold_id",
        "split",
        "season",
        "round_number",
        "event_order",
        "split_strategy",
    ]
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
        validation_sessions = set(fold.get("validation_session_ids", []))
        test_sessions = set(fold.get("test_session_ids", []))
        if train_sessions & validation_sessions:
            raise ValueError(f"validation session leaked into train sessions for {fold}")
        if train_sessions & test_sessions:
            raise ValueError(f"test session leaked into train sessions for {fold}")

    if str(metadata.get("split_strategy") or "") in {"temporal_expanding", "temporal_year"}:
        rows_by_fold: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in rows:
            rows_by_fold[str(row.get("fold_id"))].append(row)
        for fold_id, fold_rows in rows_by_fold.items():
            train_orders: list[int] = []
            eval_orders: list[int] = []
            for row in fold_rows:
                order = to_int(row.get("event_order"))
                if order is None:
                    continue
                if row.get("split") == "train":
                    train_orders.append(order)
                elif row.get("split") in {"validation", "test", "holdout"}:
                    eval_orders.append(order)
            if train_orders and eval_orders and max(train_orders) >= min(eval_orders):
                raise ValueError(f"future session leaked into training rows for fold {fold_id}")


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
    polars.DataFrame(
        result.rows,
        schema=DATASET_COLUMNS,
        infer_schema_length=None,
    ).write_parquet(dataset_path)
    metadata_path.write_text(json.dumps(result.metadata, indent=2, sort_keys=True) + "\n")


def build_dataset_from_db(
    connection: QueryConnection,
    *,
    session_ids: tuple[str, ...] = DEMO_SESSION_IDS,
    split_strategy: str = "loro",
    train_years: tuple[int, ...] = (),
    validation_years: tuple[int, ...] = (),
    test_years: tuple[int, ...] = (),
    target_strategy: str = "lap_time_delta",
) -> DatasetBuildResult:
    """Refresh clean-air diagnostics, load DB laps, and build the dataset."""

    refresh_clean_air_lap_times(connection)
    rows = load_clean_pace_laps(connection, session_ids=session_ids)
    if split_strategy == "loro":
        result = build_loro_dataset(rows, target_strategy=target_strategy)
        _attach_raw_session_quality(result.metadata, rows, session_ids)
        return result
    if split_strategy == "temporal_expanding":
        result = build_temporal_expanding_dataset(rows, target_strategy=target_strategy)
        _attach_raw_session_quality(result.metadata, rows, session_ids)
        return result
    if split_strategy == "temporal_year":
        result = build_temporal_year_dataset(
            rows,
            train_years=train_years,
            validation_years=validation_years,
            test_years=test_years,
            target_strategy=target_strategy,
        )
        _attach_raw_session_quality(result.metadata, rows, session_ids)
        return result
    raise ValueError(f"unsupported split_strategy: {split_strategy}")


def _build_dataset_row(
    row: Mapping[str, Any],
    fold: FoldSpec,
    references: ReferencePace,
    driver_offsets: DriverOffsetLookup,
    *,
    split: str,
    split_strategy: str,
    event_order: int | None,
    target_strategy: str,
    past_references: Mapping[tuple[int, str], float],
) -> dict[str, Any]:
    reference, reference_source = _target_reference_for_row(
        row,
        references,
        target_strategy=target_strategy,
        past_references=past_references,
    )
    lap_time_ms = to_float(row.get("lap_time_ms"))
    target = _target_for_row(lap_time_ms, reference, target_strategy=target_strategy)
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
        "season": to_int(row.get("season")),
        "round_number": to_int(row.get("round_number")),
        "event_order": event_order,
        "split_strategy": split_strategy,
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
        "split": split,
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


def _target_reference_for_row(
    row: Mapping[str, Any],
    references: ReferencePace,
    *,
    target_strategy: str,
    past_references: Mapping[tuple[int, str], float],
) -> tuple[float | None, str]:
    if target_strategy == "absolute_lap_time":
        reference, source = _reference_for_row(row, references)
        return reference, f"feature_{source}"
    if target_strategy == "session_normalized_delta":
        past_key = (id(row), "session")
        if past_key in past_references:
            return past_references[past_key], "past_session_compound"
    if target_strategy == "stint_relative_delta":
        past_key = (id(row), "stint")
        if past_key in past_references:
            return past_references[past_key], "past_stint"
    if target_strategy == "season_circuit_compound_delta":
        season = to_int(row.get("season"))
        circuit_id = str(row.get("circuit_id") or "")
        compound = str(row.get("compound") or "").upper()
        key = (season, circuit_id, compound) if season is not None else None
        if key in references.by_season_circuit_compound:
            return references.by_season_circuit_compound[key], "season_circuit_compound"
    return _reference_for_row(row, references)


def _target_for_row(
    lap_time_ms: float | None,
    reference: float | None,
    *,
    target_strategy: str,
) -> float | None:
    if lap_time_ms is None:
        return None
    if target_strategy == "absolute_lap_time":
        return lap_time_ms
    if reference is None:
        return None
    return lap_time_ms - reference


def _compute_past_references(
    rows: Sequence[Mapping[str, Any]],
) -> dict[tuple[int, str], float]:
    """Precompute live-safe past references without reading future laps."""

    refs: dict[tuple[int, str], float] = {}
    session_values: dict[tuple[str, str], list[float]] = defaultdict(list)
    stint_values: dict[tuple[str, str, int], list[float]] = defaultdict(list)
    ordered_rows = sorted(
        rows,
        key=lambda row: (
            str(row.get("session_id") or ""),
            to_int(row.get("lap_number")) or 0,
            str(row.get("driver_code") or ""),
        ),
    )
    for row in ordered_rows:
        session_id = str(row.get("session_id") or "")
        compound = str(row.get("compound") or "").upper()
        driver_code = str(row.get("driver_code") or "")
        stint_number = to_int(row.get("stint_number")) or 0
        lap_time_ms = to_float(row.get("lap_time_ms"))
        session_key = (session_id, compound)
        stint_key = (session_id, driver_code, stint_number)
        if session_values[session_key]:
            refs[(id(row), "session")] = float(median(session_values[session_key]))
        if stint_values[stint_key]:
            refs[(id(row), "stint")] = float(median(stint_values[stint_key]))
        if lap_time_ms is not None:
            session_values[session_key].append(lap_time_ms)
            stint_values[stint_key].append(lap_time_ms)
    return refs


def _validate_target_strategy(target_strategy: str) -> None:
    if target_strategy not in VALID_TARGET_STRATEGIES:
        raise ValueError(f"unsupported target_strategy: {target_strategy}")


def _attach_raw_session_quality(
    metadata: dict[str, Any],
    raw_rows: Sequence[Mapping[str, Any]],
    requested_session_ids: Sequence[str],
) -> None:
    requested = [session_id for session_id in requested_session_ids if session_id]
    included = set(str(session_id) for session_id in metadata.get("sessions_included", []))
    raw_by_session: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in raw_rows:
        raw_by_session[str(row.get("session_id") or "")].append(row)
    metadata["requested_session_count"] = len(requested)
    metadata["zero_usable_sessions"] = [
        {
            "session_id": session_id,
            "raw_rows": len(raw_by_session.get(session_id, [])),
            "dominant_reason": _dominant_zero_usable_reason(raw_by_session.get(session_id, [])),
        }
        for session_id in requested
        if session_id not in included
    ]


def _dominant_zero_usable_reason(rows: Sequence[Mapping[str, Any]]) -> str:
    if not rows:
        return "no_raw_rows_loaded"
    compounds = {str(row.get("compound") or "").upper() for row in rows}
    if compounds - VALID_XGB_COMPOUNDS:
        return "unsupported_or_missing_compound"
    if any(str(row.get("track_status") or "GREEN").upper() != "GREEN" for row in rows):
        return "non_green_or_mixed_conditions"
    if any(to_bool(row.get("is_pit_in_lap")) or to_bool(row.get("is_pit_out_lap")) for row in rows):
        return "pit_laps_only"
    return "filtered_by_clean_lap_rules"


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
    record["season"] = to_int(record.get("season"))
    record["round_number"] = to_int(record.get("round_number"))
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
    *,
    split_strategy: str,
    session_orders: Sequence[SessionOrder],
    final_test_status: str,
    target_strategy: str,
) -> dict[str, Any]:
    usable_rows = [row for row in rows if row.get("row_usable") is True]
    return {
        "row_count": len(rows),
        "usable_row_count": len(usable_rows),
        "feature_columns": FEATURE_COLUMNS,
        "target_column": TARGET_COLUMN,
        "target_strategy": target_strategy,
        "target_definition": _target_definition(target_strategy),
        "baseline_reference_source": _baseline_reference_source(target_strategy),
        "sessions_included": session_ids,
        "split_strategy": split_strategy,
        "session_chronology": [
            {
                "session_id": row.session_id,
                "season": row.season,
                "round_number": row.round_number,
                "event_order": row.event_order,
            }
            for row in session_orders
        ],
        "final_test_status": final_test_status,
        "folds": [
            {
                "fold_id": fold.fold_id,
                "holdout_session_id": fold.holdout_session_id,
                "train_session_ids": list(fold.train_session_ids),
                "validation_session_ids": list(fold.validation_session_ids),
                "test_session_ids": list(fold.test_session_ids),
                "train_event_orders": list(fold.train_event_orders),
                "validation_event_orders": list(fold.validation_event_orders),
                "test_event_orders": list(fold.test_event_orders),
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
            f"{split_strategy} by session chronology",
            "holdout reference pace uses training sessions only",
            "holdout driver offsets use training sessions only",
            "live-style target strategies use only past in-session laps when applicable",
            "temporal validation/test sessions are never used to compute train references",
            "pit loss excluded from lap-level pace dataset",
        ],
        "generated_at": generated_at.isoformat(),
        "known_limitations": [
            "dataset quality depends on manifest ingestion coverage",
            "traffic represented by simple gap proxies",
            "categorical encoding deferred to Day 8 training",
            "no pit-loss or pair-level undercut outcome features in this dataset",
        ],
    }


def _target_definition(target_strategy: str) -> str:
    definitions = {
        "lap_time_delta": "lap_time_ms minus fold-training reference_lap_time_ms",
        "session_normalized_delta": (
            "lap_time_ms minus median prior clean dry laps in the same session+compound; "
            "falls back to fold-training reference"
        ),
        "stint_relative_delta": (
            "lap_time_ms minus median prior clean dry laps in the same driver stint; "
            "falls back to fold-training reference"
        ),
        "absolute_lap_time": (
            "raw clean lap_time_ms stored in lap_time_delta_ms "
            "for experiment compatibility"
        ),
        "season_circuit_compound_delta": (
            "lap_time_ms minus fold-training season+circuit+compound median; "
            "falls back to circuit+compound and global compound"
        ),
    }
    return definitions[target_strategy]


def _baseline_reference_source(target_strategy: str) -> str:
    sources = {
        "lap_time_delta": "fold_train_circuit_compound_or_global_compound",
        "session_normalized_delta": "past_session_compound_then_fold_train_reference",
        "stint_relative_delta": "past_driver_stint_then_fold_train_reference",
        "absolute_lap_time": "none_target_is_absolute_lap_time",
        "season_circuit_compound_delta": "fold_train_season_circuit_compound",
    }
    return sources[target_strategy]


def _infer_session_orders(rows: Sequence[Mapping[str, Any]]) -> list[SessionOrder]:
    by_session: dict[str, tuple[int, int]] = {}
    for row in rows:
        session_id = str(row.get("session_id") or "")
        season = to_int(row.get("season"))
        round_number = to_int(row.get("round_number"))
        if not session_id:
            continue
        if season is None or round_number is None:
            season, round_number = _parse_session_id_order(session_id)
        by_session[session_id] = (season, round_number)
    return _session_orders_from_tuples(
        (session_id, season, round_number)
        for session_id, (season, round_number) in by_session.items()
    )


def _session_orders_from_tuples(
    sessions: Iterable[tuple[str, int, int]],
) -> list[SessionOrder]:
    unique: dict[str, tuple[int, int]] = {}
    for session_id, season, round_number in sessions:
        if not session_id:
            continue
        unique[str(session_id)] = (int(season), int(round_number))
    ordered = sorted(unique.items(), key=lambda item: (item[1][0], item[1][1], item[0]))
    return [
        SessionOrder(
            session_id=session_id,
            season=season_round[0],
            round_number=season_round[1],
            event_order=index,
        )
        for index, (session_id, season_round) in enumerate(ordered, start=1)
    ]


def _default_temporal_block_size(session_orders: Sequence[SessionOrder]) -> int:
    counts_by_year: dict[int, int] = defaultdict(int)
    for row in session_orders:
        counts_by_year[row.season] += 1
    max_year_count = max(counts_by_year.values(), default=len(session_orders))
    if max_year_count >= 12:
        return max(1, ceil(max_year_count / 3))
    return max(1, len(session_orders) // 3)


def _parse_session_id_order(session_id: str) -> tuple[int, int]:
    parts = session_id.rsplit("_", 2)
    if len(parts) >= 2:
        try:
            return int(parts[-2]), 999
        except ValueError:
            pass
    return 9999, 999


def _sql_text(sql: str) -> Any:
    sqlalchemy = import_module("sqlalchemy")
    return sqlalchemy.text(sql)
