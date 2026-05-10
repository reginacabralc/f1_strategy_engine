#!/usr/bin/env python
"""Validate demo race ingestion counts in the local DB."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import text

from pitwall.db.engine import create_db_engine

COUNT_SQL = text(
    """
    WITH demo AS (
        SELECT
            s.session_id,
            e.name AS event_name,
            e.round_number
        FROM sessions s
        JOIN events e ON e.event_id = s.event_id
        WHERE e.season = 2024
          AND e.round_number IN (1, 8, 13)
          AND s.session_type = 'R'
    ),
    lap_counts AS (
        SELECT session_id, COUNT(*) AS laps
        FROM laps
        GROUP BY session_id
    ),
    stint_counts AS (
        SELECT session_id, COUNT(*) AS stints
        FROM stints
        GROUP BY session_id
    ),
    pit_counts AS (
        SELECT session_id, COUNT(*) AS pit_stops
        FROM pit_stops
        GROUP BY session_id
    ),
    weather_counts AS (
        SELECT session_id, COUNT(*) AS weather
        FROM weather
        GROUP BY session_id
    )
    SELECT
        demo.session_id,
        demo.event_name,
        demo.round_number,
        COALESCE(lap_counts.laps, 0) AS laps,
        COALESCE(stint_counts.stints, 0) AS stints,
        COALESCE(pit_counts.pit_stops, 0) AS pit_stops,
        COALESCE(weather_counts.weather, 0) AS weather
    FROM demo
    LEFT JOIN lap_counts ON lap_counts.session_id = demo.session_id
    LEFT JOIN stint_counts ON stint_counts.session_id = demo.session_id
    LEFT JOIN pit_counts ON pit_counts.session_id = demo.session_id
    LEFT JOIN weather_counts ON weather_counts.session_id = demo.session_id
    ORDER BY demo.round_number
    """
)

CLEAN_LAPS_SQL = text(
    """
    SELECT
        session_id,
        compound,
        COUNT(*) AS clean_laps
    FROM laps
    WHERE is_valid = TRUE
      AND is_pit_in = FALSE
      AND is_pit_out = FALSE
      AND track_status = 'GREEN'
      AND lap_time_ms BETWEEN 60000 AND 180000
    GROUP BY session_id, compound
    ORDER BY session_id, compound
    """
)


def main() -> int:
    engine = create_db_engine()
    with engine.connect() as connection:
        count_rows = [dict(row._mapping) for row in connection.execute(COUNT_SQL)]
        clean_rows = [dict(row._mapping) for row in connection.execute(CLEAN_LAPS_SQL)]

    print("Demo session counts")
    print_table(
        count_rows,
        ["round_number", "session_id", "laps", "stints", "pit_stops", "weather"],
    )
    print("\nClean lap availability")
    print_table(clean_rows, ["session_id", "compound", "clean_laps"])

    if len(count_rows) != 3:
        raise SystemExit(f"Expected 3 demo race sessions, found {len(count_rows)}")
    for row in count_rows:
        for key in ("laps", "stints", "pit_stops", "weather"):
            if int(row[key] or 0) <= 0:
                raise SystemExit(f"{row['session_id']} has no {key}")
    if not clean_rows:
        raise SystemExit("No clean laps found for degradation input")
    return 0


def print_table(rows: Iterable[dict[str, Any]], columns: list[str]) -> None:
    rows = list(rows)
    widths = {
        column: max([len(column), *(len(str(row.get(column, ""))) for row in rows)])
        for column in columns
    }
    print(" | ".join(column.ljust(widths[column]) for column in columns))
    print("-+-".join("-" * widths[column] for column in columns))
    for row in rows:
        print(
            " | ".join(
                str(row.get(column, "")).ljust(widths[column]) for column in columns
            )
        )


if __name__ == "__main__":
    raise SystemExit(main())
