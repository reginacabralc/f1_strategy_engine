"""Canonicalize the Hungary demo session slug.

Revision ID: 0003_canonical_hungary_slug
Revises: 0002_clean_air_lap_times
Create Date: 2026-05-10
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_canonical_hungary_slug"
down_revision: str | None = "0002_clean_air_lap_times"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Repair local DBs loaded before the Hungarian GP slug override landed."""

    op.execute(
        """
        INSERT INTO circuits (
            circuit_id,
            name,
            country,
            pit_lane_loss_seconds,
            pit_lane_speed_limit,
            typical_race_laps
        )
        SELECT
            'hungary',
            name,
            country,
            pit_lane_loss_seconds,
            pit_lane_speed_limit,
            typical_race_laps
        FROM circuits
        WHERE circuit_id = 'hungarian'
        ON CONFLICT (circuit_id) DO UPDATE SET
            name = EXCLUDED.name,
            country = EXCLUDED.country,
            pit_lane_loss_seconds = EXCLUDED.pit_lane_loss_seconds,
            pit_lane_speed_limit = EXCLUDED.pit_lane_speed_limit,
            typical_race_laps = EXCLUDED.typical_race_laps
        """
    )
    op.execute(
        """
        UPDATE events
        SET circuit_id = 'hungary'
        WHERE circuit_id = 'hungarian'
        """
    )
    op.execute(
        """
        INSERT INTO sessions (session_id, event_id, session_type, date, total_laps)
        SELECT 'hungary_2024_R', event_id, session_type, date, total_laps
        FROM sessions
        WHERE session_id = 'hungarian_2024_R'
        ON CONFLICT (session_id) DO UPDATE SET
            event_id = EXCLUDED.event_id,
            session_type = EXCLUDED.session_type,
            date = EXCLUDED.date,
            total_laps = EXCLUDED.total_laps
        """
    )
    for table_name in (
        "laps",
        "pit_stops",
        "stints",
        "track_status_events",
        "weather",
        "known_undercuts",
        "replay_runs",
        "alerts",
    ):
        op.execute(
            f"""
            UPDATE {table_name}
            SET session_id = 'hungary_2024_R'
            WHERE session_id = 'hungarian_2024_R'
            """
        )
    op.execute(
        """
        DELETE FROM sessions
        WHERE session_id = 'hungarian_2024_R'
        """
    )
    op.execute(
        """
        DELETE FROM degradation_coefficients old_coeff
        WHERE old_coeff.circuit_id = 'hungarian'
          AND EXISTS (
              SELECT 1
              FROM degradation_coefficients new_coeff
              WHERE new_coeff.circuit_id = 'hungary'
                AND new_coeff.compound = old_coeff.compound
          )
        """
    )
    op.execute(
        """
        UPDATE degradation_coefficients
        SET circuit_id = 'hungary'
        WHERE circuit_id = 'hungarian'
        """
    )
    op.execute(
        """
        DELETE FROM circuits
        WHERE circuit_id = 'hungarian'
          AND NOT EXISTS (
              SELECT 1 FROM events WHERE circuit_id = 'hungarian'
          )
          AND NOT EXISTS (
              SELECT 1 FROM degradation_coefficients WHERE circuit_id = 'hungarian'
          )
          AND NOT EXISTS (
              SELECT 1 FROM pit_loss_estimates WHERE circuit_id = 'hungarian'
          )
          AND NOT EXISTS (
              SELECT 1 FROM driver_skill_offsets WHERE circuit_id = 'hungarian'
          )
        """
    )
    op.execute("REFRESH MATERIALIZED VIEW clean_air_lap_times")


def downgrade() -> None:
    """Leave canonical session IDs in place on downgrade."""

