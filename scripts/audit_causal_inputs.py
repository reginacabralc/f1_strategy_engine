#!/usr/bin/env python
"""Audit Phase 1 inputs for the causal undercut module.

This script does not build labels or train anything. It only reports whether the
historical DB has the columns and coverage needed before Phase 3 can build a
driver-rival-lap dataset.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import text

from pitwall.db.engine import create_db_engine

SESSION_COVERAGE_SQL = text(
    """
    SELECT
        l.session_id,
        COUNT(*) AS lap_rows,
        COUNT(l.lap_time_ms) AS lap_time_rows,
        COUNT(l.position) AS position_rows,
        COUNT(l.gap_to_leader_ms) AS gap_to_leader_rows,
        COUNT(l.gap_to_ahead_ms) AS gap_to_ahead_rows,
        COUNT(l.compound) AS compound_rows,
        COUNT(l.tyre_age) AS tyre_age_rows,
        COUNT(*) FILTER (WHERE l.track_status IS NOT NULL) AS track_status_rows,
        COUNT(*) FILTER (WHERE l.is_pit_in OR l.is_pit_out) AS pit_flag_rows,
        COUNT(*) FILTER (WHERE l.is_valid = TRUE) AS valid_rows
    FROM laps l
    GROUP BY l.session_id
    ORDER BY l.session_id
    """
)

WEATHER_COVERAGE_SQL = text(
    """
    SELECT
        session_id,
        COUNT(*) AS weather_rows,
        COUNT(track_temp_c) AS track_temp_rows,
        COUNT(air_temp_c) AS air_temp_rows,
        COUNT(rainfall) AS rainfall_rows
    FROM weather
    GROUP BY session_id
    ORDER BY session_id
    """
)

TRACK_STATUS_SQL = text(
    """
    SELECT
        COALESCE(track_status, 'NULL') AS track_status,
        COUNT(*) AS lap_rows
    FROM laps
    GROUP BY COALESCE(track_status, 'NULL')
    ORDER BY track_status
    """
)

ARTIFACT_SQL = text(
    """
    SELECT 'sessions' AS artifact, COUNT(*) AS rows FROM sessions
    UNION ALL
    SELECT 'laps' AS artifact, COUNT(*) AS rows FROM laps
    UNION ALL
    SELECT 'stints' AS artifact, COUNT(*) AS rows FROM stints
    UNION ALL
    SELECT 'pit_stops' AS artifact, COUNT(*) AS rows FROM pit_stops
    UNION ALL
    SELECT 'weather' AS artifact, COUNT(*) AS rows FROM weather
    UNION ALL
    SELECT 'degradation_coefficients' AS artifact, COUNT(*) AS rows
    FROM degradation_coefficients
    UNION ALL
    SELECT 'pit_loss_estimates' AS artifact, COUNT(*) AS rows
    FROM pit_loss_estimates
    UNION ALL
    SELECT 'driver_skill_offsets' AS artifact, COUNT(*) AS rows
    FROM driver_skill_offsets
    UNION ALL
    SELECT 'known_undercuts' AS artifact, COUNT(*) AS rows
    FROM known_undercuts
    ORDER BY artifact
    """
)


def main() -> int:
    engine = create_db_engine()
    with engine.connect() as connection:
        session_rows = rows_as_dicts(connection.execute(SESSION_COVERAGE_SQL))
        weather_rows = rows_as_dicts(connection.execute(WEATHER_COVERAGE_SQL))
        track_status_rows = rows_as_dicts(connection.execute(TRACK_STATUS_SQL))
        artifact_rows = rows_as_dicts(connection.execute(ARTIFACT_SQL))

    print("Causal input audit")
    print()
    print("Core artifacts")
    print_table(artifact_rows, ["artifact", "rows"])
    print()
    print("Lap coverage by session")
    print_table(
        session_rows,
        [
            "session_id",
            "lap_rows",
            "lap_time_rows",
            "position_rows",
            "gap_to_leader_rows",
            "gap_to_ahead_rows",
            "compound_rows",
            "tyre_age_rows",
            "track_status_rows",
            "pit_flag_rows",
            "valid_rows",
        ],
    )
    print()
    print("Weather coverage by session")
    print_table(
        weather_rows,
        ["session_id", "weather_rows", "track_temp_rows", "air_temp_rows", "rainfall_rows"],
    )
    print()
    print("Track status lap rows")
    print_table(track_status_rows, ["track_status", "lap_rows"])
    print()
    print_gap_decision(session_rows)
    print_label_readiness(artifact_rows)
    return 0


def rows_as_dicts(rows: Iterable[Any]) -> list[dict[str, Any]]:
    return [dict(row._mapping) for row in rows]


def print_gap_decision(session_rows: list[dict[str, Any]]) -> None:
    if not session_rows:
        print("Gap audit: no lap rows found. Run migrate + ingest-demo first.")
        return

    total_laps = sum(int(row["lap_rows"] or 0) for row in session_rows)
    ahead_rows = sum(int(row["gap_to_ahead_rows"] or 0) for row in session_rows)
    leader_rows = sum(int(row["gap_to_leader_rows"] or 0) for row in session_rows)

    print("Gap audit decision")
    if ahead_rows == 0 and leader_rows == 0:
        print(
            "- GAP_RECONSTRUCTION_REQUIRED: no gap_to_ahead_ms or gap_to_leader_ms "
            "values were found."
        )
        print(
            "- Do not build undercut_viable labels until cumulative race gaps are "
            "derived or another trusted gap source is loaded."
        )
    else:
        ahead_pct = 100.0 * ahead_rows / max(1, total_laps)
        leader_pct = 100.0 * leader_rows / max(1, total_laps)
        print(
            f"- Gap coverage exists: gap_to_ahead_ms={ahead_pct:.1f}% "
            f"gap_to_leader_ms={leader_pct:.1f}%."
        )
        if ahead_pct < 90.0:
            print("- CAUTION: gap_to_ahead_ms coverage is below 90%; labels need source flags.")
        else:
            print("- OK: gap_to_ahead_ms coverage is sufficient for Phase 3 labels.")


def print_label_readiness(artifact_rows: list[dict[str, Any]]) -> None:
    counts = {str(row["artifact"]): int(row["rows"] or 0) for row in artifact_rows}
    print()
    print("Label readiness")
    required = ("laps", "stints", "pit_stops", "weather", "degradation_coefficients")
    missing = [name for name in required if counts.get(name, 0) == 0]
    if missing:
        print(f"- BLOCKED: missing required artifact rows: {', '.join(missing)}")
    else:
        print("- Base historical inputs are present.")
    if counts.get("pit_loss_estimates", 0) == 0:
        print("- BLOCKED: pit_loss_estimates is empty; run make fit-pit-loss.")
    if counts.get("known_undercuts", 0) == 0:
        print("- NOTE: known_undercuts is empty; success evaluation will be proxy-only.")


def print_table(rows: Iterable[dict[str, Any]], columns: list[str]) -> None:
    rows = list(rows)
    if not rows:
        print("(no rows)")
        return
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
