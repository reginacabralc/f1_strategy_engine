"""Derive observed pit-cycle undercut attempts from historical lap data."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy import text

from pitwall.ingest.normalize import to_bool, to_int

AUTO_DERIVED_NOTES_PREFIX = "auto_derived_pit_cycle_v1"
DEFAULT_MAX_PRE_PIT_GAP_MS = 30_000
DEFAULT_MAX_DEFENDER_RESPONSE_LAPS = 8
DEFAULT_EVAL_SETTLE_LAPS = 1


class QueryConnection(Protocol):
    def execute(self, statement: object, parameters: object | None = None) -> Any: ...


@dataclass(frozen=True, slots=True)
class LapCycleInput:
    session_id: str
    driver_code: str
    lap_number: int
    position: int | None
    gap_to_ahead_ms: int | None
    is_pit_in: bool
    is_pit_out: bool
    ts: datetime


@dataclass(frozen=True, slots=True)
class KnownUndercut:
    session_id: str
    attacker_code: str
    defender_code: str
    lap_of_attempt: int
    was_successful: bool
    notes: str


LOAD_LAP_CYCLE_INPUTS_SQL = text(
    """
    SELECT
        session_id,
        driver_code,
        lap_number,
        position,
        gap_to_ahead_ms,
        is_pit_in,
        is_pit_out,
        ts
    FROM laps
    ORDER BY session_id, lap_number, position NULLS LAST, driver_code, ts
    """
)

LOAD_LAP_CYCLE_INPUTS_FOR_SESSIONS_SQL = text(
    """
    SELECT
        session_id,
        driver_code,
        lap_number,
        position,
        gap_to_ahead_ms,
        is_pit_in,
        is_pit_out,
        ts
    FROM laps
    WHERE session_id = ANY(:session_ids)
    ORDER BY session_id, lap_number, position NULLS LAST, driver_code, ts
    """
)

DELETE_AUTO_DERIVED_SQL = text(
    """
    DELETE FROM known_undercuts
    WHERE notes LIKE :notes_prefix
    """
)

INSERT_KNOWN_UNDERCUT_SQL = text(
    """
    INSERT INTO known_undercuts (
        session_id,
        attacker_code,
        defender_code,
        lap_of_attempt,
        was_successful,
        notes
    )
    VALUES (
        :session_id,
        :attacker_code,
        :defender_code,
        :lap_of_attempt,
        :was_successful,
        :notes
    )
    ON CONFLICT DO NOTHING
    """
)


def load_lap_cycle_inputs(
    connection: QueryConnection,
    *,
    session_ids: tuple[str, ...] = (),
) -> list[LapCycleInput]:
    """Load lap rows needed to derive observed pit-cycle undercut attempts."""

    if session_ids:
        rows = connection.execute(
            LOAD_LAP_CYCLE_INPUTS_FOR_SESSIONS_SQL,
            {"session_ids": list(session_ids)},
        )
    else:
        rows = connection.execute(LOAD_LAP_CYCLE_INPUTS_SQL)
    return [lap_cycle_input_from_mapping(row._mapping) for row in rows]


def write_known_undercuts(
    connection: QueryConnection,
    rows: Iterable[KnownUndercut],
    *,
    replace_auto_derived: bool = True,
) -> int:
    """Persist derived undercut rows without overwriting manual curated rows."""

    payload = [
        {
            "session_id": row.session_id,
            "attacker_code": row.attacker_code,
            "defender_code": row.defender_code,
            "lap_of_attempt": row.lap_of_attempt,
            "was_successful": row.was_successful,
            "notes": row.notes,
        }
        for row in rows
    ]
    if replace_auto_derived:
        connection.execute(
            DELETE_AUTO_DERIVED_SQL,
            {"notes_prefix": f"{AUTO_DERIVED_NOTES_PREFIX}%"},
        )
    if not payload:
        return 0
    connection.execute(INSERT_KNOWN_UNDERCUT_SQL, payload)
    return len(payload)


def derive_known_undercuts(
    rows: Iterable[LapCycleInput],
    *,
    max_pre_pit_gap_ms: int = DEFAULT_MAX_PRE_PIT_GAP_MS,
    max_defender_response_laps: int = DEFAULT_MAX_DEFENDER_RESPONSE_LAPS,
    eval_settle_laps: int = DEFAULT_EVAL_SETTLE_LAPS,
) -> list[KnownUndercut]:
    """Derive conservative observed undercut attempts from pit-cycle exchanges.

    A row is emitted when an attacker pits from directly behind a defender and
    the defender pits within the response window. Success is judged after both
    pit cycles have completed by comparing race positions on the evaluation lap.
    """

    rows_list = sorted(
        rows,
        key=lambda row: (
            row.session_id,
            row.lap_number,
            row.position if row.position is not None else 999,
            row.driver_code,
        ),
    )
    by_lap = _rows_by_lap(rows_list)
    by_driver_lap = {
        (row.session_id, row.driver_code, row.lap_number): row for row in rows_list
    }
    pit_in_laps = _pit_laps_by_driver(rows_list, pit_in=True)
    pit_out_laps = _pit_laps_by_driver(rows_list, pit_in=False)
    candidates: list[KnownUndercut] = []

    for row in rows_list:
        if not row.is_pit_in:
            continue
        pre_lap = row.lap_number - 1
        pre_row = by_driver_lap.get((row.session_id, row.driver_code, pre_lap))
        if not _eligible_pre_pit_attacker(pre_row, max_pre_pit_gap_ms=max_pre_pit_gap_ms):
            continue
        assert pre_row is not None
        defender_row = _row_at_position(
            by_lap.get((row.session_id, pre_lap), []),
            position=pre_row.position - 1 if pre_row.position is not None else None,
        )
        if defender_row is None:
            continue
        defender_pit_in_lap = _first_lap_between(
            pit_in_laps.get((row.session_id, defender_row.driver_code), []),
            start=row.lap_number + 1,
            end=row.lap_number + max_defender_response_laps,
        )
        if defender_pit_in_lap is None:
            continue
        attacker_pit_out_lap = _first_lap_between(
            pit_out_laps.get((row.session_id, row.driver_code), []),
            start=row.lap_number,
            end=defender_pit_in_lap + eval_settle_laps + 2,
        )
        defender_pit_out_lap = _first_lap_between(
            pit_out_laps.get((row.session_id, defender_row.driver_code), []),
            start=defender_pit_in_lap,
            end=defender_pit_in_lap + 2,
        )
        if attacker_pit_out_lap is None or defender_pit_out_lap is None:
            continue
        eval_lap = defender_pit_out_lap + eval_settle_laps
        attacker_eval = by_driver_lap.get((row.session_id, row.driver_code, eval_lap))
        defender_eval = by_driver_lap.get((row.session_id, defender_row.driver_code, eval_lap))
        if attacker_eval is None or defender_eval is None:
            continue
        if attacker_eval.position is None or defender_eval.position is None:
            continue

        was_successful = attacker_eval.position < defender_eval.position
        candidates.append(
            KnownUndercut(
                session_id=row.session_id,
                attacker_code=row.driver_code,
                defender_code=defender_row.driver_code,
                lap_of_attempt=row.lap_number,
                was_successful=was_successful,
                notes=_notes(
                    pre_lap=pre_lap,
                    pre_gap_ms=pre_row.gap_to_ahead_ms,
                    attacker_pit_out_lap=attacker_pit_out_lap,
                    defender_pit_in_lap=defender_pit_in_lap,
                    defender_pit_out_lap=defender_pit_out_lap,
                    eval_lap=eval_lap,
                    attacker_eval_position=attacker_eval.position,
                    defender_eval_position=defender_eval.position,
                ),
            )
        )
    return candidates


def lap_cycle_input_from_mapping(row: Mapping[str, Any]) -> LapCycleInput:
    """Convert a DB row mapping into a typed pit-cycle input."""

    lap_number = to_int(row.get("lap_number"))
    if lap_number is None:
        raise ValueError("lap_number is required for known-undercut derivation")
    ts = row.get("ts")
    if not isinstance(ts, datetime):
        raise ValueError("ts must be a datetime for known-undercut derivation")
    return LapCycleInput(
        session_id=str(row["session_id"]),
        driver_code=str(row["driver_code"]),
        lap_number=lap_number,
        position=to_int(row.get("position")),
        gap_to_ahead_ms=to_int(row.get("gap_to_ahead_ms")),
        is_pit_in=to_bool(row.get("is_pit_in")),
        is_pit_out=to_bool(row.get("is_pit_out")),
        ts=ts,
    )


def _eligible_pre_pit_attacker(
    row: LapCycleInput | None,
    *,
    max_pre_pit_gap_ms: int,
) -> bool:
    return (
        row is not None
        and row.position is not None
        and row.position > 1
        and row.gap_to_ahead_ms is not None
        and row.gap_to_ahead_ms <= max_pre_pit_gap_ms
    )


def _rows_by_lap(
    rows: Iterable[LapCycleInput],
) -> dict[tuple[str, int], list[LapCycleInput]]:
    by_lap: dict[tuple[str, int], list[LapCycleInput]] = defaultdict(list)
    for row in rows:
        by_lap[(row.session_id, row.lap_number)].append(row)
    return by_lap


def _pit_laps_by_driver(
    rows: Iterable[LapCycleInput],
    *,
    pit_in: bool,
) -> dict[tuple[str, str], list[int]]:
    by_driver: dict[tuple[str, str], list[int]] = defaultdict(list)
    for row in rows:
        if (pit_in and row.is_pit_in) or (not pit_in and row.is_pit_out):
            by_driver[(row.session_id, row.driver_code)].append(row.lap_number)
    return {key: sorted(laps) for key, laps in by_driver.items()}


def _row_at_position(
    rows: Iterable[LapCycleInput],
    *,
    position: int | None,
) -> LapCycleInput | None:
    if position is None:
        return None
    for row in rows:
        if row.position == position:
            return row
    return None


def _first_lap_between(
    laps: Iterable[int],
    *,
    start: int,
    end: int,
) -> int | None:
    for lap in laps:
        if start <= lap <= end:
            return lap
    return None


def _notes(
    *,
    pre_lap: int,
    pre_gap_ms: int | None,
    attacker_pit_out_lap: int,
    defender_pit_in_lap: int,
    defender_pit_out_lap: int,
    eval_lap: int,
    attacker_eval_position: int,
    defender_eval_position: int,
) -> str:
    return (
        f"{AUTO_DERIVED_NOTES_PREFIX};"
        f"pre_lap={pre_lap};"
        f"pre_gap_ms={pre_gap_ms};"
        f"attacker_pit_out_lap={attacker_pit_out_lap};"
        f"defender_pit_in_lap={defender_pit_in_lap};"
        f"defender_pit_out_lap={defender_pit_out_lap};"
        f"eval_lap={eval_lap};"
        f"attacker_eval_position={attacker_eval_position};"
        f"defender_eval_position={defender_eval_position}"
    )
