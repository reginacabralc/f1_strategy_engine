"""Build clean-air lap datasets for degradation fitting."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from importlib import import_module
from typing import Any, Protocol

from pitwall.degradation.models import VALID_FIT_COMPOUNDS
from pitwall.ingest.normalize import clean_nulls, to_bool, to_int

DEMO_SESSION_IDS = ("bahrain_2024_R", "monaco_2024_R", "hungary_2024_R")


class QueryConnection(Protocol):
    def execute(self, statement: object, parameters: Mapping[str, object] | None = None) -> Any: ...


def eligibility_for_lap(row: Mapping[str, Any]) -> tuple[bool, str | None]:
    """Return V1 clean-air fitting eligibility and a first-match exclusion reason."""

    lap_time_ms = to_int(row.get("lap_time_ms"))
    compound = _normalise_text(row.get("compound"))
    tyre_age = to_int(row.get("tyre_age"))
    track_status = _normalise_text(row.get("track_status"))

    if lap_time_ms is None:
        return False, "missing_lap_time"
    if compound not in VALID_FIT_COMPOUNDS:
        return False, "unsupported_compound"
    if tyre_age is None:
        return False, "missing_tyre_age"
    if tyre_age < 1:
        return False, "tyre_age_lt_1"
    if _row_bool(row, "is_pit_in_lap", "is_pit_in"):
        return False, "pit_in_lap"
    if _row_bool(row, "is_pit_out_lap", "is_pit_out"):
        return False, "pit_out_lap"
    if _row_bool(row, "is_deleted") or row.get("is_valid") is False:
        return False, "deleted_lap"
    if track_status is not None and track_status != "GREEN":
        return False, "non_green_track_status"
    if lap_time_ms < 60_000 or lap_time_ms > 180_000:
        return False, "invalid_lap_time"
    return True, None


def build_clean_lap_records(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Attach fitting eligibility diagnostics without dropping excluded laps."""

    records: list[dict[str, Any]] = []
    for row in rows:
        record = dict(clean_nulls(dict(row)))
        eligible, reason = eligibility_for_lap(record)
        record["fitting_eligible"] = eligible
        record["exclusion_reason"] = reason
        records.append(record)
    return records


def refresh_clean_air_lap_times(connection: QueryConnection) -> None:
    """Refresh the Day 4 materialized diagnostic dataset."""

    connection.execute(_sql_text("REFRESH MATERIALIZED VIEW clean_air_lap_times"))


def read_clean_lap_dataset(
    connection: QueryConnection,
    *,
    session_id: str | None = None,
    session_ids: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """Read clean-air diagnostic rows from the DB materialized view."""

    if session_id and session_ids:
        raise ValueError("pass either session_id or session_ids, not both")

    params: dict[str, object] = {}
    where = ""
    if session_id is not None:
        where = "WHERE c.session_id = :session_id"
        params["session_id"] = session_id
    elif session_ids:
        where = "WHERE c.session_id = ANY(:session_ids)"
        params["session_ids"] = list(session_ids)

    statement = _sql_text(
        f"""
        SELECT
            c.session_id,
            c.circuit_id,
            c.driver_code,
            c.team_code,
            c.compound,
            c.tyre_age,
            c.lap_number,
            c.stint_number,
            c.lap_time_ms,
            c.track_status,
            c.is_pit_in_lap,
            c.is_pit_out_lap,
            c.is_deleted,
            c.fitting_eligible,
            c.exclusion_reason,
            s.total_laps,
            l.position,
            l.gap_to_ahead_ms,
            l.gap_to_leader_ms
        FROM clean_air_lap_times c
        JOIN sessions s ON s.session_id = c.session_id
        LEFT JOIN laps l
          ON l.session_id = c.session_id
         AND l.driver_code = c.driver_code
         AND l.lap_number = c.lap_number
        {where}
        ORDER BY c.session_id, c.compound, c.driver_code, c.lap_number
        """
    )
    rows = connection.execute(statement, params)
    return [dict(row._mapping) for row in rows]


def _row_bool(row: Mapping[str, Any], *keys: str) -> bool:
    for key in keys:
        if key in row:
            return to_bool(row.get(key))
    return False


def _normalise_text(value: Any) -> str | None:
    value = clean_nulls(value)
    return str(value).strip().upper() if value is not None else None


def _sql_text(sql: str) -> Any:
    sqlalchemy = import_module("sqlalchemy")
    return sqlalchemy.text(sql)
