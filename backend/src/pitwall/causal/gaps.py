"""Reconstruct race gaps from lap-line timing data.

The reconstructed gaps are lap-line approximations. They are suitable as a
Phase 3 prerequisite for pair-level causal labels, but downstream causal
datasets should mark them with ``gap_source='reconstructed_fastf1_time'``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from itertools import groupby
from typing import Any, Protocol

from sqlalchemy import text

from pitwall.ingest.normalize import to_int


class QueryConnection(Protocol):
    def execute(self, statement: object, parameters: object | None = None) -> Any: ...


@dataclass(frozen=True, slots=True)
class LapGapInput:
    session_id: str
    driver_code: str
    lap_number: int
    ts: datetime
    lap_time_ms: int | None
    position: int | None


@dataclass(frozen=True, slots=True)
class LapGapUpdate:
    session_id: str
    driver_code: str
    lap_number: int
    ts: datetime
    gap_to_leader_ms: int | None
    gap_to_ahead_ms: int | None


@dataclass(frozen=True, slots=True)
class GapSessionSummary:
    session_id: str
    rows: int
    gap_to_leader_rows: int
    gap_to_ahead_rows: int


LOAD_GAP_INPUTS_SQL = text(
    """
    SELECT
        session_id,
        driver_code,
        lap_number,
        ts,
        lap_time_ms,
        position
    FROM laps
    ORDER BY session_id, lap_number, position NULLS LAST, driver_code, ts
    """
)

LOAD_GAP_INPUTS_FOR_SESSIONS_SQL = text(
    """
    SELECT
        session_id,
        driver_code,
        lap_number,
        ts,
        lap_time_ms,
        position
    FROM laps
    WHERE session_id = ANY(:session_ids)
    ORDER BY session_id, lap_number, position NULLS LAST, driver_code, ts
    """
)

UPDATE_GAPS_SQL = text(
    """
    UPDATE laps
    SET
        gap_to_leader_ms = :gap_to_leader_ms,
        gap_to_ahead_ms = :gap_to_ahead_ms
    WHERE session_id = :session_id
      AND driver_code = :driver_code
      AND lap_number = :lap_number
      AND ts = :ts
    """
)


def load_gap_inputs(
    connection: QueryConnection,
    *,
    session_ids: tuple[str, ...] = (),
) -> list[LapGapInput]:
    """Load lap rows needed to reconstruct lap-line race gaps."""

    if session_ids:
        rows = connection.execute(
            LOAD_GAP_INPUTS_FOR_SESSIONS_SQL,
            {"session_ids": list(session_ids)},
        )
    else:
        rows = connection.execute(LOAD_GAP_INPUTS_SQL)
    return [lap_gap_input_from_mapping(row._mapping) for row in rows]


def write_gap_updates(
    connection: QueryConnection,
    updates: Iterable[LapGapUpdate],
) -> int:
    """Persist reconstructed gap columns for the supplied lap rows."""

    payload = [
        {
            "session_id": update.session_id,
            "driver_code": update.driver_code,
            "lap_number": update.lap_number,
            "ts": update.ts,
            "gap_to_leader_ms": update.gap_to_leader_ms,
            "gap_to_ahead_ms": update.gap_to_ahead_ms,
        }
        for update in updates
    ]
    if not payload:
        return 0
    connection.execute(UPDATE_GAPS_SQL, payload)
    return len(payload)


def reconstruct_gap_updates(rows: Iterable[LapGapInput]) -> list[LapGapUpdate]:
    """Return gap updates using lap-end timestamps within each session.

    ``laps.ts`` is derived by ingestion from FastF1's lap ``Time`` field. That
    makes it a better source for line-crossing gaps than summing ``lap_time_ms``,
    because a missing lap time does not poison later laps for that driver.
    """

    sorted_rows = sorted(
        rows,
        key=lambda row: (
            row.session_id,
            row.lap_number,
            _position_sort(row.position),
            row.driver_code,
            row.ts,
        ),
    )
    updates: list[LapGapUpdate] = []
    for session_id, session_rows in _group_by_session(sorted_rows):
        for _lap_number, lap_rows_iter in _group_by_lap(session_rows):
            lap_rows = list(lap_rows_iter)
            ranked_rows = [row for row in lap_rows if row.position is not None]
            ranked_rows.sort(
                key=lambda row: (
                    row.position if row.position is not None else 999,
                    row.ts,
                    row.driver_code,
                )
            )
            gaps_by_key = _gaps_for_ranked_rows(ranked_rows)
            for row in lap_rows:
                gap_to_leader_ms, gap_to_ahead_ms = gaps_by_key.get(
                    _lap_key(row),
                    (None, None),
                )
                updates.append(
                    LapGapUpdate(
                        session_id=session_id,
                        driver_code=row.driver_code,
                        lap_number=row.lap_number,
                        ts=row.ts,
                        gap_to_leader_ms=gap_to_leader_ms,
                        gap_to_ahead_ms=gap_to_ahead_ms,
                    )
                )
    return updates


def summarize_gap_updates(
    updates: Iterable[LapGapUpdate],
) -> list[GapSessionSummary]:
    """Summarize reconstructed gap coverage by session."""

    summaries: dict[str, dict[str, int]] = defaultdict(
        lambda: {"rows": 0, "gap_to_leader_rows": 0, "gap_to_ahead_rows": 0}
    )
    for update in updates:
        summary = summaries[update.session_id]
        summary["rows"] += 1
        if update.gap_to_leader_ms is not None:
            summary["gap_to_leader_rows"] += 1
        if update.gap_to_ahead_ms is not None:
            summary["gap_to_ahead_rows"] += 1
    return [
        GapSessionSummary(
            session_id=session_id,
            rows=values["rows"],
            gap_to_leader_rows=values["gap_to_leader_rows"],
            gap_to_ahead_rows=values["gap_to_ahead_rows"],
        )
        for session_id, values in sorted(summaries.items())
    ]


def lap_gap_input_from_mapping(row: Mapping[str, Any]) -> LapGapInput:
    """Convert a DB row mapping into a typed reconstruction input."""

    lap_number = to_int(row.get("lap_number"))
    if lap_number is None:
        raise ValueError("lap_number is required for gap reconstruction")
    ts = row.get("ts")
    if not isinstance(ts, datetime):
        raise ValueError("ts must be a datetime for gap reconstruction")
    return LapGapInput(
        session_id=str(row["session_id"]),
        driver_code=str(row["driver_code"]),
        lap_number=lap_number,
        ts=ts,
        lap_time_ms=to_int(row.get("lap_time_ms")),
        position=to_int(row.get("position")),
    )


def _gaps_for_ranked_rows(
    rows: list[LapGapInput],
) -> dict[tuple[str, int, str, datetime], tuple[int | None, int | None]]:
    if not rows:
        return {}
    leader_ts = rows[0].ts
    previous_ts: datetime | None = None
    gaps: dict[tuple[str, int, str, datetime], tuple[int | None, int | None]] = {}
    for row in rows:
        gap_to_leader_ms = _positive_delta_ms(row.ts, leader_ts)
        gap_to_ahead_ms = None if previous_ts is None else _positive_delta_ms(row.ts, previous_ts)
        gaps[_lap_key(row)] = (gap_to_leader_ms, gap_to_ahead_ms)
        previous_ts = row.ts
    return gaps


def _positive_delta_ms(later: datetime, earlier: datetime) -> int:
    return max(0, round((later - earlier).total_seconds() * 1000))


def _group_by_session(rows: Iterable[LapGapInput]) -> Iterator[tuple[str, Iterator[LapGapInput]]]:
    return groupby(rows, key=lambda row: row.session_id)


def _group_by_lap(rows: Iterable[LapGapInput]) -> Iterator[tuple[int, Iterator[LapGapInput]]]:
    return groupby(rows, key=lambda row: row.lap_number)


def _lap_key(row: LapGapInput) -> tuple[str, int, str, datetime]:
    return (row.session_id, row.lap_number, row.driver_code, row.ts)


def _position_sort(position: int | None) -> int:
    return position if position is not None else 999
