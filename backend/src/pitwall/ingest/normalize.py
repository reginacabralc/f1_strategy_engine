"""Normalize FastF1 session data into PitWall's internal ingest shape."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, timedelta
from math import isfinite, isnan
from typing import Any, cast

VALID_COMPOUNDS = {"SOFT", "MEDIUM", "HARD", "INTER", "WET"}
TRACK_STATUS_MAP = {
    "1": "GREEN",
    "2": "YELLOW",
    "4": "SC",
    "5": "RED",
    "6": "VSC",
    "7": "VSC",
}

Record = dict[str, Any]


def dataframe_to_records(data: Any) -> list[Record]:
    """Convert a dataframe-like object or iterable of mappings into records."""

    if data is None:
        return []
    if hasattr(data, "to_dict"):
        try:
            return [dict(row) for row in data.to_dict(orient="records")]
        except TypeError:
            pass
    if isinstance(data, Mapping):
        return [dict(data)]
    return [dict(row) for row in data]


def clean_nulls(value: Any) -> Any:
    """Recursively convert NaN/NaT-like values to ``None``."""

    if value is None:
        return None
    if isinstance(value, Mapping):
        return {str(key): clean_nulls(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean_nulls(item) for item in value]
    if isinstance(value, tuple):
        return [clean_nulls(item) for item in value]
    if isinstance(value, float) and isnan(value):
        return None
    try:
        if value != value:
            return None
    except (TypeError, ValueError):
        return value
    if str(value) in {"NaT", "<NA>", "nan"}:
        return None
    return value


def first_present(row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in row:
            value = clean_nulls(row[name])
            if value is not None:
                return value
    return None


def timedelta_to_ms(value: Any) -> int | None:
    """Convert timedelta-like values to whole milliseconds."""

    value = clean_nulls(value)
    if value is None:
        return None
    if isinstance(value, (int, float)) and isfinite(value):
        return round(float(value))
    if isinstance(value, timedelta) or hasattr(value, "total_seconds"):
        return round(float(value.total_seconds()) * 1000)
    return None


def to_int(value: Any) -> int | None:
    value = clean_nulls(value)
    if value is None:
        return None
    try:
        if isinstance(value, float) and isnan(value):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def to_float(value: Any) -> float | None:
    value = clean_nulls(value)
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def to_bool(value: Any) -> bool:
    value = clean_nulls(value)
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "t", "yes", "y"}
    return bool(value)


def normalize_compound(value: Any) -> str | None:
    value = clean_nulls(value)
    if value is None:
        return None
    compound = str(value).strip().upper()
    return compound if compound in VALID_COMPOUNDS else None


def normalize_track_status(value: Any) -> str | None:
    value = clean_nulls(value)
    if value is None:
        return None
    status = str(value).strip().upper()
    known_statuses = set(TRACK_STATUS_MAP.values())
    return TRACK_STATUS_MAP.get(status, status if status in known_statuses else None)


def event_timestamp(session_start: datetime | None, offset: Any) -> str | None:
    if isinstance(offset, datetime):
        return ensure_tz(offset).isoformat()
    offset_ms = timedelta_to_ms(offset)
    if session_start is None or offset_ms is None:
        return None
    return (ensure_tz(session_start) + timedelta(milliseconds=offset_ms)).isoformat()


def ensure_tz(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def slugify(value: str) -> str:
    slug = value.lower()
    slug = re.sub(r"\b(grand prix|gp|formula 1|f1)\b", "", slug)
    slug = re.sub(r"[^a-z0-9]+", "_", slug).strip("_")
    return slug or "unknown"


def build_session_id(event: Mapping[str, Any] | Any, year: int, session_code: str) -> str:
    """Build a deterministic session id such as ``monaco_2024_R``."""

    event_record = dict(event) if isinstance(event, Mapping) else {}
    location = first_present(event_record, "Location", "EventName", "OfficialEventName", "Name")
    if location is None and hasattr(event, "get"):
        location = event.get("Location") or event.get("EventName")
    return f"{slugify(str(location or 'unknown'))}_{year}_{session_code}"


def normalize_laps(
    laps: Iterable[Mapping[str, Any]] | Any,
    *,
    session_id: str,
    session_start: datetime | None = None,
) -> list[Record]:
    """Normalize FastF1 lap rows without silently dropping invalid laps."""

    rows: list[Record] = []
    for raw in dataframe_to_records(laps):
        driver_code = first_present(raw, "Driver", "DriverNumber", "Abbreviation")
        lap_number = to_int(first_present(raw, "LapNumber", "Lap"))
        if driver_code is None or lap_number is None:
            continue

        row = {
            "session_id": session_id,
            "driver_code": str(driver_code),
            "lap_number": lap_number,
            "lap_time_ms": timedelta_to_ms(first_present(raw, "LapTime")),
            "sector_1_ms": timedelta_to_ms(first_present(raw, "Sector1Time")),
            "sector_2_ms": timedelta_to_ms(first_present(raw, "Sector2Time")),
            "sector_3_ms": timedelta_to_ms(first_present(raw, "Sector3Time")),
            "compound": normalize_compound(first_present(raw, "Compound")),
            "tyre_age": to_int(first_present(raw, "TyreLife", "TyreAge")),
            "stint_number": to_int(first_present(raw, "Stint", "StintNumber")),
            "position": to_int(first_present(raw, "Position")),
            "is_pit_in_lap": first_present(raw, "PitInTime", "PitInLap") is not None,
            "is_pit_out_lap": first_present(raw, "PitOutTime", "PitOutLap") is not None,
            "is_deleted": to_bool(first_present(raw, "Deleted", "IsDeleted")),
            "track_status": normalize_track_status(first_present(raw, "TrackStatus")),
            "ts": event_timestamp(session_start, first_present(raw, "Time", "LapStartTime")),
        }
        rows.append(clean_nulls(row))
    return rows


def reconstruct_stints(laps: Iterable[Mapping[str, Any]]) -> list[Record]:
    """Reconstruct stints from normalized lap rows."""

    by_driver: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in laps:
        session_id = str(row["session_id"])
        driver_code = str(row["driver_code"])
        by_driver.setdefault((session_id, driver_code), []).append(row)

    stints: list[Record] = []
    for (session_id, driver_code), rows in sorted(by_driver.items()):
        sorted_rows = sorted(rows, key=lambda row: int(row["lap_number"]))
        current: Record | None = None
        last_tyre_age: int | None = None
        next_stint_number = 1

        for row in sorted_rows:
            compound = clean_nulls(row.get("compound"))
            lap_number = to_int(row.get("lap_number"))
            tyre_age = to_int(row.get("tyre_age"))
            explicit_stint = to_int(row.get("stint_number"))
            if compound is None or lap_number is None:
                continue

            starts_new = current is None
            if current is not None:
                starts_new = (
                    (explicit_stint is not None and explicit_stint != current["stint_number"])
                    or compound != current["compound"]
                    or (
                        last_tyre_age is not None
                        and tyre_age is not None
                        and tyre_age < last_tyre_age
                    )
                    or (to_bool(row.get("is_pit_out_lap")) and lap_number != current["lap_start"])
                )

            if starts_new:
                if current is not None:
                    stints.append(clean_nulls(current))
                stint_number = explicit_stint or next_stint_number
                next_stint_number = max(next_stint_number, stint_number + 1)
                current = {
                    "session_id": session_id,
                    "driver_code": driver_code,
                    "stint_number": stint_number,
                    "compound": compound,
                    "lap_start": lap_number,
                    "lap_end": lap_number,
                    "age_at_start": tyre_age or 0,
                }
            elif current is not None:
                current["lap_end"] = lap_number

            last_tyre_age = tyre_age

        if current is not None:
            stints.append(clean_nulls(current))

    return stints


def normalize_drivers(
    results: Iterable[Mapping[str, Any]] | Any,
    *,
    session_id: str,
) -> list[Record]:
    rows: list[Record] = []
    for raw in dataframe_to_records(results):
        driver_code = first_present(raw, "Abbreviation", "Driver", "BroadcastName")
        if driver_code is None:
            continue
        rows.append(
            clean_nulls(
                {
                    "session_id": session_id,
                    "driver_code": str(driver_code),
                    "driver_number": str(first_present(raw, "DriverNumber") or ""),
                    "full_name": first_present(raw, "FullName", "FullName"),
                    "team_name": first_present(raw, "TeamName", "Team"),
                    "team_color": first_present(raw, "TeamColor"),
                }
            )
        )
    return rows


def normalize_weather(
    weather: Iterable[Mapping[str, Any]] | Any,
    *,
    session_id: str,
    session_start: datetime | None = None,
) -> list[Record]:
    rows: list[Record] = []
    for raw in dataframe_to_records(weather):
        rows.append(
            clean_nulls(
                {
                    "session_id": session_id,
                    "ts": event_timestamp(session_start, first_present(raw, "Time", "Date")),
                    "lap_number": to_int(first_present(raw, "LapNumber", "Lap")),
                    "track_temp_c": to_float(first_present(raw, "TrackTemp")),
                    "air_temp_c": to_float(first_present(raw, "AirTemp")),
                    "humidity_pct": to_float(first_present(raw, "Humidity")),
                    "rainfall": (
                        None
                        if first_present(raw, "Rainfall") is None
                        else to_bool(first_present(raw, "Rainfall"))
                    ),
                }
            )
        )
    return rows


def normalize_pit_stops(laps: Iterable[Mapping[str, Any]]) -> list[Record]:
    """Build pit stop markers from normalized lap pit flags."""

    stops: list[Record] = []
    for row in laps:
        if not to_bool(row.get("is_pit_in_lap")) and not to_bool(row.get("is_pit_out_lap")):
            continue
        stops.append(
            clean_nulls(
                {
                    "session_id": row.get("session_id"),
                    "driver_code": row.get("driver_code"),
                    "lap_number": row.get("lap_number"),
                    "duration_ms": None,
                    "pit_loss_ms": None,
                    "new_compound": (
                        row.get("compound") if to_bool(row.get("is_pit_out_lap")) else None
                    ),
                    "ts": row.get("ts"),
                    "source": "laps",
                }
            )
        )
    return stops


def normalize_metadata(
    *,
    session_id: str,
    year: int,
    round_number: int,
    session_code: str,
    event: Mapping[str, Any],
    session_start: datetime | date | None,
    total_laps: int | None,
) -> Record:
    if isinstance(session_start, datetime):
        session_date = session_start.date().isoformat()
        session_start_value = ensure_tz(session_start).isoformat()
    elif isinstance(session_start, date):
        session_date = session_start.isoformat()
        session_start_value = session_start.isoformat()
    else:
        session_date = None
        session_start_value = None

    return cast(
        Record,
        clean_nulls(
            {
                "session_id": session_id,
                "year": year,
                "round": round_number,
                "session": session_code,
                "event_name": first_present(event, "EventName", "OfficialEventName", "Name"),
                "location": first_present(event, "Location"),
                "country": first_present(event, "Country"),
                "date": session_date,
                "session_start": session_start_value,
                "total_laps": total_laps,
            }
        ),
    )
