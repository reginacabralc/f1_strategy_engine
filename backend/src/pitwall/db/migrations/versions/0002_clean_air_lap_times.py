"""Enrich clean-air fitting view and coefficient metrics.

Revision ID: 0002_clean_air_lap_times
Revises: 0001_initial_schema
Create Date: 2026-05-10
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_clean_air_lap_times"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS clean_air_lap_times")
    op.execute(
        """
        ALTER TABLE degradation_coefficients
            ADD COLUMN IF NOT EXISTS model_type TEXT NOT NULL DEFAULT 'quadratic_v1',
            ADD COLUMN IF NOT EXISTS rmse_ms REAL CHECK (rmse_ms IS NULL OR rmse_ms >= 0),
            ADD COLUMN IF NOT EXISTS n_laps INT CHECK (n_laps IS NULL OR n_laps > 0),
            ADD COLUMN IF NOT EXISTS min_tyre_age INT CHECK (
                min_tyre_age IS NULL OR min_tyre_age >= 0
            ),
            ADD COLUMN IF NOT EXISTS max_tyre_age INT CHECK (
                max_tyre_age IS NULL OR max_tyre_age >= min_tyre_age
            ),
            ADD COLUMN IF NOT EXISTS source_sessions TEXT[]
        """
    )
    op.execute(
        """
        CREATE MATERIALIZED VIEW clean_air_lap_times AS
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
            CASE
                WHEN l.lap_time_ms IS NULL THEN FALSE
                WHEN l.compound IS NULL OR l.compound NOT IN ('SOFT','MEDIUM','HARD') THEN FALSE
                WHEN l.tyre_age IS NULL THEN FALSE
                WHEN l.tyre_age < 1 THEN FALSE
                WHEN l.is_pit_in THEN FALSE
                WHEN l.is_pit_out THEN FALSE
                WHEN NOT l.is_valid THEN FALSE
                WHEN l.track_status IS NOT NULL AND l.track_status <> 'GREEN' THEN FALSE
                WHEN l.lap_time_ms NOT BETWEEN 60000 AND 180000 THEN FALSE
                ELSE TRUE
            END AS fitting_eligible,
            CASE
                WHEN l.lap_time_ms IS NULL THEN 'missing_lap_time'
                WHEN l.compound IS NULL OR l.compound NOT IN ('SOFT','MEDIUM','HARD')
                    THEN 'unsupported_compound'
                WHEN l.tyre_age IS NULL THEN 'missing_tyre_age'
                WHEN l.tyre_age < 1 THEN 'tyre_age_lt_1'
                WHEN l.is_pit_in THEN 'pit_in_lap'
                WHEN l.is_pit_out THEN 'pit_out_lap'
                WHEN NOT l.is_valid THEN 'deleted_lap'
                WHEN l.track_status IS NOT NULL AND l.track_status <> 'GREEN'
                    THEN 'non_green_track_status'
                WHEN l.lap_time_ms NOT BETWEEN 60000 AND 180000 THEN 'invalid_lap_time'
                ELSE NULL
            END AS exclusion_reason,
            l.ts
        FROM laps l
        JOIN sessions s ON s.session_id = l.session_id
        JOIN events e ON e.event_id = s.event_id
        LEFT JOIN drivers d ON d.driver_code = l.driver_code
        LEFT JOIN stints st
            ON st.session_id = l.session_id
           AND st.driver_code = l.driver_code
           AND l.lap_number BETWEEN st.lap_start AND COALESCE(st.lap_end, l.lap_number)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_clean_air_session_driver
        ON clean_air_lap_times (session_id, driver_code, lap_number)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_clean_air_fit_group
        ON clean_air_lap_times (circuit_id, compound, fitting_eligible)
        """
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS clean_air_lap_times")
    op.execute(
        """
        ALTER TABLE degradation_coefficients
            DROP COLUMN IF EXISTS source_sessions,
            DROP COLUMN IF EXISTS max_tyre_age,
            DROP COLUMN IF EXISTS min_tyre_age,
            DROP COLUMN IF EXISTS n_laps,
            DROP COLUMN IF EXISTS rmse_ms,
            DROP COLUMN IF EXISTS model_type
        """
    )
    op.execute(
        """
        CREATE MATERIALIZED VIEW clean_air_lap_times AS
        SELECT
            session_id,
            driver_code,
            lap_number,
            lap_time_ms,
            compound,
            tyre_age,
            position,
            ts
        FROM laps
        WHERE is_valid     = TRUE
          AND is_pit_in    = FALSE
          AND is_pit_out   = FALSE
          AND track_status = 'GREEN'
          AND lap_time_ms BETWEEN 60000 AND 180000
        """
    )
    op.execute(
        """
        CREATE INDEX idx_clean_air_session_driver
        ON clean_air_lap_times (session_id, driver_code, lap_number)
        """
    )
