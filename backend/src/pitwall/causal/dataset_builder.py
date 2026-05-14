"""Build the Phase 3/4 driver-rival-lap causal dataset."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import text

from pitwall.causal.labels import (
    ViabilityInputs,
    build_degradation_lookup,
    compute_undercut_viability_label,
)
from pitwall.engine.pit_loss import DEFAULT_PIT_LOSS_MS, GLOBAL_FALLBACK_CIRCUIT_ID
from pitwall.ingest.normalize import clean_nulls, to_bool, to_float, to_int

DATASET_VERSION = "causal_driver_rival_lap_v1"
GAP_SOURCE = "reconstructed_fastf1_time"
PACE_SOURCE = "causal_scipy"

CAUSAL_DATASET_COLUMNS = [
    "session_id",
    "circuit_id",
    "season",
    "lap_number",
    "total_laps",
    "laps_remaining",
    "race_phase",
    "attacker_code",
    "defender_code",
    "attacker_team_code",
    "defender_team_code",
    "current_position",
    "rival_position",
    "gap_to_rival_ms",
    "current_gap_to_car_ahead_ms",
    "attacker_gap_to_leader_ms",
    "defender_gap_to_leader_ms",
    "attacker_lap_time_ms",
    "defender_lap_time_ms",
    "attacker_compound",
    "defender_compound",
    "attacker_next_compound",
    "attacker_tyre_age",
    "defender_tyre_age",
    "tyre_age_delta",
    "attacker_stint_number",
    "defender_stint_number",
    "attacker_laps_in_stint",
    "defender_laps_in_stint",
    "track_status",
    "track_temp_c",
    "air_temp_c",
    "rainfall",
    "pit_loss_estimate_ms",
    "fresh_tyre_advantage_ms",
    "projected_gain_if_pit_now_ms",
    "required_gain_to_clear_rival_ms",
    "projected_gap_after_pit_ms",
    "traffic_after_pit",
    "clean_air_potential",
    "undercut_window_open",
    "undercut_viable",
    "undercut_viable_label_source",
    "pit_now",
    "undercut_success",
    "undercut_success_label_source",
    "row_usable",
    "missing_reason",
    "gap_source",
    "pace_source",
    "label_version",
]

PAIR_LAP_QUERY = text(
    """
    WITH weather_by_lap AS (
        SELECT
            session_id,
            lap_number,
            AVG(track_temp_c)::DOUBLE PRECISION AS track_temp_c,
            AVG(air_temp_c)::DOUBLE PRECISION AS air_temp_c,
            BOOL_OR(rainfall) AS rainfall
        FROM weather
        GROUP BY session_id, lap_number
    )
    SELECT
        a.session_id,
        e.circuit_id,
        e.season,
        a.lap_number,
        s.total_laps,
        a.driver_code AS attacker_code,
        d.driver_code AS defender_code,
        ad.team_code AS attacker_team_code,
        dd.team_code AS defender_team_code,
        a.position AS current_position,
        d.position AS rival_position,
        a.gap_to_ahead_ms AS gap_to_rival_ms,
        a.gap_to_ahead_ms AS current_gap_to_car_ahead_ms,
        a.gap_to_leader_ms AS attacker_gap_to_leader_ms,
        d.gap_to_leader_ms AS defender_gap_to_leader_ms,
        a.lap_time_ms AS attacker_lap_time_ms,
        d.lap_time_ms AS defender_lap_time_ms,
        a.compound AS attacker_compound,
        d.compound AS defender_compound,
        a.tyre_age AS attacker_tyre_age,
        d.tyre_age AS defender_tyre_age,
        ast.stint_number AS attacker_stint_number,
        dst.stint_number AS defender_stint_number,
        CASE
            WHEN ast.lap_start IS NULL THEN NULL
            ELSE GREATEST(1, a.lap_number - ast.lap_start + 1)
        END AS attacker_laps_in_stint,
        CASE
            WHEN dst.lap_start IS NULL THEN NULL
            ELSE GREATEST(1, d.lap_number - dst.lap_start + 1)
        END AS defender_laps_in_stint,
        a.track_status,
        w.track_temp_c,
        w.air_temp_c,
        w.rainfall,
        a.is_pit_in AS pit_now,
        COALESCE(ple_team.pit_loss_ms, ple_circuit.pit_loss_ms, ple_global.pit_loss_ms)
            AS pit_loss_estimate_ms
    FROM laps a
    JOIN laps d
      ON d.session_id = a.session_id
     AND d.lap_number = a.lap_number
     AND d.position = a.position - 1
    JOIN sessions s ON s.session_id = a.session_id
    JOIN events e ON e.event_id = s.event_id
    LEFT JOIN drivers ad ON ad.driver_code = a.driver_code
    LEFT JOIN drivers dd ON dd.driver_code = d.driver_code
    LEFT JOIN stints ast
      ON ast.session_id = a.session_id
     AND ast.driver_code = a.driver_code
     AND a.lap_number BETWEEN ast.lap_start AND COALESCE(ast.lap_end, a.lap_number)
    LEFT JOIN stints dst
      ON dst.session_id = d.session_id
     AND dst.driver_code = d.driver_code
     AND d.lap_number BETWEEN dst.lap_start AND COALESCE(dst.lap_end, d.lap_number)
    LEFT JOIN weather_by_lap w
      ON w.session_id = a.session_id
     AND w.lap_number = a.lap_number
    LEFT JOIN pit_loss_estimates ple_team
      ON ple_team.circuit_id = e.circuit_id
     AND ple_team.team_code = ad.team_code
    LEFT JOIN pit_loss_estimates ple_circuit
      ON ple_circuit.circuit_id = e.circuit_id
     AND ple_circuit.team_code IS NULL
    LEFT JOIN pit_loss_estimates ple_global
      ON ple_global.circuit_id = :global_fallback_circuit_id
     AND ple_global.team_code IS NULL
    WHERE a.position IS NOT NULL
      AND a.position > 1
      AND (:session_ids_is_null OR a.session_id = ANY(:session_ids))
    ORDER BY a.session_id, a.lap_number, a.position
    """
)

DEGRADATION_QUERY = text(
    """
    SELECT circuit_id, compound, a, b, c, r_squared
    FROM degradation_coefficients
    WHERE model_type = 'quadratic_v1'
    """
)

KNOWN_UNDERCUT_QUERY = text(
    """
    SELECT session_id, attacker_code, defender_code, lap_of_attempt, was_successful, notes
    FROM known_undercuts
    WHERE (:session_ids_is_null OR session_id = ANY(:session_ids))
    """
)


class QueryConnection(Protocol):
    def execute(self, statement: object, parameters: Mapping[str, object] | None = None) -> Any: ...


@dataclass(frozen=True, slots=True)
class CausalDatasetBuildResult:
    rows: list[dict[str, Any]]
    metadata: dict[str, Any]


def load_pair_lap_rows(
    connection: QueryConnection,
    *,
    session_ids: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """Load consecutive driver-rival-lap observations from the DB."""

    params: dict[str, object] = {
        "session_ids": list(session_ids),
        "session_ids_is_null": not session_ids,
        "global_fallback_circuit_id": GLOBAL_FALLBACK_CIRCUIT_ID,
    }
    rows = connection.execute(PAIR_LAP_QUERY, params)
    return [dict(row._mapping) for row in rows]


def load_degradation_rows(connection: QueryConnection) -> list[dict[str, object]]:
    """Load scipy degradation coefficients for causal label construction."""

    rows = connection.execute(DEGRADATION_QUERY)
    return [dict(row._mapping) for row in rows]


def load_known_undercut_rows(
    connection: QueryConnection,
    *,
    session_ids: tuple[str, ...] = (),
) -> list[dict[str, object]]:
    """Load observed undercut outcomes used for Phase 4 success labels."""

    params: dict[str, object] = {
        "session_ids": list(session_ids),
        "session_ids_is_null": not session_ids,
    }
    rows = connection.execute(KNOWN_UNDERCUT_QUERY, params)
    return [dict(row._mapping) for row in rows]


def build_causal_dataset(
    pair_rows: Iterable[Mapping[str, Any]],
    degradation_rows: list[dict[str, object]],
    known_undercuts: Iterable[Mapping[str, object]],
    *,
    generated_at: datetime | None = None,
) -> CausalDatasetBuildResult:
    """Build Phase 3/4 causal dataset rows from pair-lap observations."""

    degradation_lookup = build_degradation_lookup(degradation_rows)
    known_lookup = _known_undercut_lookup(known_undercuts)
    rows = [
        _build_dataset_row(dict(clean_nulls(dict(row))), degradation_lookup, known_lookup)
        for row in pair_rows
    ]
    timestamp = generated_at or datetime.now(UTC)
    return CausalDatasetBuildResult(
        rows=rows,
        metadata=_build_metadata(rows, timestamp),
    )


def validate_causal_dataset_rows(
    rows: Sequence[Mapping[str, Any]],
    metadata: Mapping[str, Any],
) -> None:
    """Validate causal Phase 3/4 rows before writing."""

    if not rows:
        raise ValueError("causal undercut dataset has zero rows")
    columns = set().union(*(row.keys() for row in rows))
    missing = [column for column in CAUSAL_DATASET_COLUMNS if column not in columns]
    if missing:
        raise ValueError(f"missing causal dataset column(s): {missing}")
    usable_rows = [row for row in rows if row.get("row_usable") is True]
    if not usable_rows:
        raise ValueError("causal undercut dataset has zero usable rows")
    for row in usable_rows:
        if row.get("undercut_viable") is None:
            raise ValueError("usable row has NULL undercut_viable")
        if row.get("gap_source") != GAP_SOURCE:
            raise ValueError("causal row has unexpected gap_source")
        if row.get("pace_source") != PACE_SOURCE:
            raise ValueError("causal row has unexpected pace_source")
        if row.get("pit_now") and row.get("undercut_success") is None:
            continue
    if metadata.get("dataset_version") != DATASET_VERSION:
        raise ValueError("metadata dataset_version does not match causal dataset")


def write_causal_dataset(
    result: CausalDatasetBuildResult,
    *,
    dataset_path: Path,
    metadata_path: Path,
) -> None:
    """Write causal dataset parquet and metadata JSON artifacts."""

    validate_causal_dataset_rows(result.rows, result.metadata)
    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    polars = import_module("polars")
    (
        polars.DataFrame(result.rows, infer_schema_length=None)
        .select(CAUSAL_DATASET_COLUMNS)
        .write_parquet(dataset_path)
    )
    metadata_path.write_text(json.dumps(result.metadata, indent=2, sort_keys=True) + "\n")


def build_causal_dataset_from_db(
    connection: QueryConnection,
    *,
    session_ids: tuple[str, ...] = (),
) -> CausalDatasetBuildResult:
    """Load DB inputs and build the Phase 3/4 causal dataset."""

    return build_causal_dataset(
        load_pair_lap_rows(connection, session_ids=session_ids),
        load_degradation_rows(connection),
        load_known_undercut_rows(connection, session_ids=session_ids),
    )


def _build_dataset_row(
    row: Mapping[str, Any],
    degradation_lookup: dict[tuple[str, str], Any],
    known_lookup: dict[tuple[str, str, str, int], tuple[bool, str]],
) -> dict[str, Any]:
    lap_number = to_int(row.get("lap_number"))
    total_laps = to_int(row.get("total_laps"))
    laps_remaining = (
        max(0, total_laps - lap_number)
        if lap_number is not None and total_laps is not None
        else None
    )
    race_phase = _race_phase(lap_number, total_laps)
    gap_to_rival_ms = to_int(row.get("gap_to_rival_ms"))
    pit_loss_estimate_ms = to_int(row.get("pit_loss_estimate_ms")) or DEFAULT_PIT_LOSS_MS
    attacker_tyre_age = to_int(row.get("attacker_tyre_age"))
    defender_tyre_age = to_int(row.get("defender_tyre_age"))
    label = compute_undercut_viability_label(
        ViabilityInputs(
            circuit_id=str(row.get("circuit_id") or ""),
            attacker_compound=_text(row.get("attacker_compound")),
            defender_compound=_text(row.get("defender_compound")),
            attacker_tyre_age=attacker_tyre_age,
            defender_tyre_age=defender_tyre_age,
            gap_to_rival_ms=gap_to_rival_ms,
            pit_loss_estimate_ms=pit_loss_estimate_ms,
            track_status=_text(row.get("track_status")),
            rainfall=to_bool(row.get("rainfall")),
            attacker_laps_in_stint=to_int(row.get("attacker_laps_in_stint")),
            defender_laps_in_stint=to_int(row.get("defender_laps_in_stint")),
        ),
        degradation_lookup,
    )
    known_key = (
        str(row.get("session_id")),
        str(row.get("attacker_code")),
        str(row.get("defender_code")),
        lap_number or -1,
    )
    success = known_lookup.get(known_key)
    success_value = success[0] if success is not None else None
    success_source = success[1] if success is not None else None
    undercut_viable = label.undercut_viable
    undercut_viable_source = label.label_source
    undercut_window_open = label.undercut_window_open
    row_usable = label.row_usable
    missing_reason = label.missing_reason
    if success_value is not None:
        undercut_viable = success_value or bool(label.undercut_viable)
        undercut_window_open = bool(undercut_viable)
        undercut_viable_source = f"observed_{success_source}"
        row_usable = True
        missing_reason = None
    projected_gap = label.projected_gap_after_pit_ms

    return {
        "session_id": row.get("session_id"),
        "circuit_id": row.get("circuit_id"),
        "season": to_int(row.get("season")),
        "lap_number": lap_number,
        "total_laps": total_laps,
        "laps_remaining": laps_remaining,
        "race_phase": race_phase,
        "attacker_code": row.get("attacker_code"),
        "defender_code": row.get("defender_code"),
        "attacker_team_code": row.get("attacker_team_code"),
        "defender_team_code": row.get("defender_team_code"),
        "current_position": to_int(row.get("current_position")),
        "rival_position": to_int(row.get("rival_position")),
        "gap_to_rival_ms": gap_to_rival_ms,
        "current_gap_to_car_ahead_ms": to_int(row.get("current_gap_to_car_ahead_ms")),
        "attacker_gap_to_leader_ms": to_int(row.get("attacker_gap_to_leader_ms")),
        "defender_gap_to_leader_ms": to_int(row.get("defender_gap_to_leader_ms")),
        "attacker_lap_time_ms": to_int(row.get("attacker_lap_time_ms")),
        "defender_lap_time_ms": to_int(row.get("defender_lap_time_ms")),
        "attacker_compound": _text(row.get("attacker_compound")),
        "defender_compound": _text(row.get("defender_compound")),
        "attacker_next_compound": label.next_compound,
        "attacker_tyre_age": attacker_tyre_age,
        "defender_tyre_age": defender_tyre_age,
        "tyre_age_delta": (
            defender_tyre_age - attacker_tyre_age
            if defender_tyre_age is not None and attacker_tyre_age is not None
            else None
        ),
        "attacker_stint_number": to_int(row.get("attacker_stint_number")),
        "defender_stint_number": to_int(row.get("defender_stint_number")),
        "attacker_laps_in_stint": to_int(row.get("attacker_laps_in_stint")),
        "defender_laps_in_stint": to_int(row.get("defender_laps_in_stint")),
        "track_status": _text(row.get("track_status")) or "GREEN",
        "track_temp_c": to_float(row.get("track_temp_c")),
        "air_temp_c": to_float(row.get("air_temp_c")),
        "rainfall": to_bool(row.get("rainfall")),
        "pit_loss_estimate_ms": pit_loss_estimate_ms,
        "fresh_tyre_advantage_ms": label.fresh_tyre_advantage_ms,
        "projected_gain_if_pit_now_ms": label.projected_gain_if_pit_now_ms,
        "required_gain_to_clear_rival_ms": label.required_gain_to_clear_rival_ms,
        "projected_gap_after_pit_ms": projected_gap,
        "traffic_after_pit": _traffic_bucket(projected_gap),
        "clean_air_potential": _clean_air_potential(projected_gap),
        "undercut_window_open": undercut_window_open,
        "undercut_viable": undercut_viable,
        "undercut_viable_label_source": undercut_viable_source,
        "pit_now": to_bool(row.get("pit_now")),
        "undercut_success": success_value,
        "undercut_success_label_source": success_source,
        "row_usable": row_usable,
        "missing_reason": missing_reason,
        "gap_source": GAP_SOURCE,
        "pace_source": PACE_SOURCE,
        "label_version": DATASET_VERSION,
    }


def _known_undercut_lookup(
    rows: Iterable[Mapping[str, object]],
) -> dict[tuple[str, str, str, int], tuple[bool, str]]:
    lookup: dict[tuple[str, str, str, int], tuple[bool, str]] = {}
    for row in rows:
        lap = to_int(row.get("lap_of_attempt"))
        if lap is None:
            continue
        notes = str(row.get("notes") or "")
        source = "auto_derived_pit_cycle_v1" if notes.startswith("auto_derived") else "curated"
        lookup[
            (
                str(row.get("session_id")),
                str(row.get("attacker_code")),
                str(row.get("defender_code")),
                lap,
            )
        ] = (to_bool(row.get("was_successful")), source)
    return lookup


def _build_metadata(rows: Sequence[Mapping[str, Any]], generated_at: datetime) -> dict[str, Any]:
    usable_rows = [row for row in rows if row.get("row_usable") is True]
    viable_rows = [row for row in usable_rows if row.get("undercut_viable") is True]
    observed_success_rows = [row for row in rows if row.get("undercut_success") is not None]
    return {
        "dataset_version": DATASET_VERSION,
        "row_count": len(rows),
        "usable_row_count": len(usable_rows),
        "undercut_viable_rows": len(viable_rows),
        "observed_success_rows": len(observed_success_rows),
        "feature_source": "driver-rival-lap consecutive race order pairs",
        "pace_source": PACE_SOURCE,
        "gap_source": GAP_SOURCE,
        "target_columns": ["undercut_viable", "undercut_success"],
        "generated_at": generated_at.isoformat(),
        "leakage_policy": [
            "features use lap-t observations only",
            "pit_now is treatment/outcome context, not a viability input",
            "known_undercuts joins only into undercut_success outcome labels",
            "XGBoost features, predictions, and importances are not used",
        ],
    }


def _race_phase(lap_number: int | None, total_laps: int | None) -> str | None:
    if lap_number is None or total_laps is None or total_laps <= 0:
        return None
    progress = lap_number / total_laps
    if progress < 0.33:
        return "early"
    if progress < 0.66:
        return "mid"
    return "late"


def _traffic_bucket(projected_gap_after_pit_ms: int | None) -> str:
    if projected_gap_after_pit_ms is None:
        return "unknown"
    if projected_gap_after_pit_ms <= 0:
        return "low"
    if projected_gap_after_pit_ms <= 3_000:
        return "medium"
    return "high"


def _clean_air_potential(projected_gap_after_pit_ms: int | None) -> str:
    if projected_gap_after_pit_ms is None:
        return "unknown"
    if projected_gap_after_pit_ms <= 0:
        return "high"
    if projected_gap_after_pit_ms <= 3_000:
        return "medium"
    return "low"


def _text(value: object) -> str | None:
    if value is None:
        return None
    return str(value).upper()
