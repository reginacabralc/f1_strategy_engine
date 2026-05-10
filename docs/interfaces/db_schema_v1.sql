-- ============================================================================
-- PitWall — Database Schema v1
-- ============================================================================
-- Owner:    Stream A (with review from Streams B and D).
-- Status:   Proposed at Day 1 kickoff. Finalised once all 4 streams confirm.
-- Related:  ADR 0001 (stack), ADR 0003 (TimescaleDB).
--
-- This file is the *agreed schema reference*. The runtime source of truth
-- is the Alembic migration set in `backend/src/pitwall/db/migrations/`
-- (Stream A, Day 3). When a migration is added, mirror the change here
-- and append a row to the CHANGELOG below.
--
-- TimescaleDB constraint: any UNIQUE or PRIMARY KEY index on a hypertable
-- must include the partitioning column. We therefore include `ts` in the
-- composite PK of the `laps` hypertable. Duplicate
-- `(session_id, driver_code, lap_number)` tuples with different `ts`
-- values cannot occur in practice (FastF1 emits one timestamp per lap),
-- so the application layer does not need to enforce uniqueness on the
-- shorter natural key.
-- ============================================================================
-- CHANGELOG
--   2026-05-09  v1   Initial schema (Day 1 kickoff).
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ----------------------------------------------------------------------------
-- 1. Reference catalogues
-- ----------------------------------------------------------------------------

CREATE TABLE circuits (
    circuit_id              TEXT        PRIMARY KEY,
    name                    TEXT        NOT NULL,
    country                 TEXT,
    pit_lane_loss_seconds   REAL        CHECK (pit_lane_loss_seconds IS NULL
                                                OR pit_lane_loss_seconds > 0),
    pit_lane_speed_limit    INT         CHECK (pit_lane_speed_limit IS NULL
                                                OR pit_lane_speed_limit > 0),
    typical_race_laps       INT         CHECK (typical_race_laps IS NULL
                                                OR typical_race_laps > 0)
);

CREATE TABLE seasons (
    season                  INT         PRIMARY KEY CHECK (season >= 1950),
    regulations             TEXT
);

CREATE TABLE events (
    event_id                TEXT        PRIMARY KEY,
    season                  INT         NOT NULL REFERENCES seasons(season),
    circuit_id              TEXT        NOT NULL REFERENCES circuits(circuit_id),
    round_number            INT         NOT NULL CHECK (round_number > 0),
    name                    TEXT        NOT NULL,
    start_date              DATE        NOT NULL,
    UNIQUE (season, round_number)
);

CREATE TABLE sessions (
    session_id              TEXT        PRIMARY KEY,
    event_id                TEXT        NOT NULL REFERENCES events(event_id),
    session_type            TEXT        NOT NULL CHECK (session_type IN
                                            ('FP1','FP2','FP3','Q','SQ','S','R')),
    date                    DATE        NOT NULL,
    total_laps              INT         CHECK (total_laps IS NULL OR total_laps > 0)
);
CREATE INDEX idx_sessions_event ON sessions (event_id);

CREATE TABLE teams (
    team_code               TEXT        PRIMARY KEY,
    full_name               TEXT
);

-- V1 supports a single (driver_code -> team_code) mapping. V2 will
-- introduce a composite PK (driver_code, season) when multi-season
-- ingestion is enabled and a driver may have changed teams across years.
CREATE TABLE drivers (
    driver_code             TEXT        PRIMARY KEY,
    full_name               TEXT,
    team_code               TEXT        REFERENCES teams(team_code)
);

-- ----------------------------------------------------------------------------
-- 2. Time-series fact tables
-- ----------------------------------------------------------------------------
-- Only `laps` is a hypertable in V1. All other fact tables remain regular
-- Postgres tables: their volume is far too low to justify chunking and
-- they are not subject to time-bucket aggregations in the V1 query set.
-- ----------------------------------------------------------------------------

CREATE TABLE laps (
    session_id              TEXT        NOT NULL REFERENCES sessions(session_id),
    -- driver_code intentionally has no FK: see the `drivers` table note above.
    driver_code             TEXT        NOT NULL,
    lap_number              INT         NOT NULL CHECK (lap_number > 0),
    lap_time_ms             INT         CHECK (lap_time_ms IS NULL OR lap_time_ms > 0),
    sector_1_ms             INT,
    sector_2_ms             INT,
    sector_3_ms             INT,
    compound                TEXT        CHECK (compound IS NULL OR compound IN
                                            ('SOFT','MEDIUM','HARD','INTER','WET')),
    tyre_age                INT         CHECK (tyre_age IS NULL OR tyre_age >= 0),
    is_pit_in               BOOLEAN     NOT NULL DEFAULT FALSE,
    is_pit_out              BOOLEAN     NOT NULL DEFAULT FALSE,
    is_valid                BOOLEAN     NOT NULL DEFAULT TRUE,
    track_status            TEXT        CHECK (track_status IS NULL OR track_status IN
                                            ('GREEN','SC','VSC','YELLOW','RED')),
    position                INT         CHECK (position IS NULL OR position > 0),
    gap_to_leader_ms        INT,
    gap_to_ahead_ms         INT,
    ts                      TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (session_id, driver_code, lap_number, ts)
);
SELECT create_hypertable('laps', 'ts', chunk_time_interval => INTERVAL '7 days');
CREATE INDEX idx_laps_session_lap ON laps (session_id, lap_number);
CREATE INDEX idx_laps_driver_ts   ON laps (driver_code, ts DESC);

CREATE TABLE pit_stops (
    session_id              TEXT        NOT NULL REFERENCES sessions(session_id),
    driver_code             TEXT        NOT NULL,
    lap_number              INT         NOT NULL CHECK (lap_number > 0),
    duration_ms             INT         CHECK (duration_ms IS NULL OR duration_ms > 0),
    pit_loss_ms             INT,
    new_compound            TEXT        CHECK (new_compound IS NULL OR new_compound IN
                                            ('SOFT','MEDIUM','HARD','INTER','WET')),
    ts                      TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (session_id, driver_code, lap_number)
);

CREATE TABLE stints (
    session_id              TEXT        NOT NULL REFERENCES sessions(session_id),
    driver_code             TEXT        NOT NULL,
    stint_number            INT         NOT NULL CHECK (stint_number > 0),
    compound                TEXT        NOT NULL CHECK (compound IN
                                            ('SOFT','MEDIUM','HARD','INTER','WET')),
    lap_start               INT         NOT NULL CHECK (lap_start > 0),
    lap_end                 INT         CHECK (lap_end IS NULL OR lap_end >= lap_start),
    age_at_start            INT         NOT NULL DEFAULT 0 CHECK (age_at_start >= 0),
    PRIMARY KEY (session_id, driver_code, stint_number)
);

CREATE TABLE track_status_events (
    session_id              TEXT        NOT NULL REFERENCES sessions(session_id),
    started_ts              TIMESTAMPTZ NOT NULL,
    ended_ts                TIMESTAMPTZ CHECK (ended_ts IS NULL OR ended_ts >= started_ts),
    lap_number              INT,
    status                  TEXT        NOT NULL CHECK (status IN
                                            ('GREEN','SC','VSC','YELLOW','RED')),
    PRIMARY KEY (session_id, started_ts)
);

-- Humidity is stored as percentage (0..100) to match FastF1's reporting.
CREATE TABLE weather (
    session_id              TEXT        NOT NULL REFERENCES sessions(session_id),
    ts                      TIMESTAMPTZ NOT NULL,
    lap_number              INT,
    track_temp_c            REAL,
    air_temp_c              REAL,
    humidity_pct            REAL        CHECK (humidity_pct IS NULL
                                                OR (humidity_pct >= 0
                                                    AND humidity_pct <= 100)),
    rainfall                BOOLEAN,
    PRIMARY KEY (session_id, ts)
);

-- ----------------------------------------------------------------------------
-- 3. Models, coefficients, aggregates
-- ----------------------------------------------------------------------------

CREATE TABLE degradation_coefficients (
    circuit_id              TEXT        NOT NULL REFERENCES circuits(circuit_id),
    compound                TEXT        NOT NULL CHECK (compound IN
                                            ('SOFT','MEDIUM','HARD','INTER','WET')),
    a                       DOUBLE PRECISION NOT NULL,
    b                       DOUBLE PRECISION NOT NULL,
    c                       DOUBLE PRECISION NOT NULL,
    r_squared               REAL        CHECK (r_squared IS NULL
                                                OR (r_squared >= 0 AND r_squared <= 1)),
    n_samples               INT         CHECK (n_samples IS NULL OR n_samples > 0),
    fitted_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (circuit_id, compound)
);

CREATE TABLE pit_loss_estimates (
    circuit_id              TEXT        NOT NULL REFERENCES circuits(circuit_id),
    team_code               TEXT        NOT NULL REFERENCES teams(team_code),
    pit_loss_ms             INT         NOT NULL CHECK (pit_loss_ms > 0),
    n_samples               INT         CHECK (n_samples IS NULL OR n_samples > 0),
    computed_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (circuit_id, team_code)
);

CREATE TABLE driver_skill_offsets (
    driver_code             TEXT        NOT NULL,
    circuit_id              TEXT        NOT NULL REFERENCES circuits(circuit_id),
    compound                TEXT        NOT NULL CHECK (compound IN
                                            ('SOFT','MEDIUM','HARD','INTER','WET')),
    offset_ms               REAL        NOT NULL,
    n_samples               INT         CHECK (n_samples IS NULL OR n_samples > 0),
    computed_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (driver_code, circuit_id, compound)
);

CREATE TABLE model_registry (
    model_id                TEXT        PRIMARY KEY,
    model_type              TEXT        NOT NULL CHECK (model_type IN
                                            ('scipy','xgboost','lstm')),
    version                 TEXT        NOT NULL,
    trained_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metrics                 JSONB,
    features                JSONB,
    train_session_ids       TEXT[],
    file_path               TEXT
);

-- ----------------------------------------------------------------------------
-- 4. Runtime artefacts
-- ----------------------------------------------------------------------------

CREATE TABLE replay_runs (
    run_id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id              TEXT        NOT NULL REFERENCES sessions(session_id),
    speed_factor            REAL        NOT NULL CHECK (speed_factor > 0),
    started_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at                TIMESTAMPTZ CHECK (ended_at IS NULL OR ended_at >= started_at),
    pace_predictor          TEXT        NOT NULL CHECK (pace_predictor IN
                                            ('scipy','xgboost')),
    note                    TEXT
);
CREATE INDEX idx_replay_runs_session ON replay_runs (session_id);

CREATE TABLE alerts (
    alert_id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                  UUID        REFERENCES replay_runs(run_id),
    session_id              TEXT        NOT NULL REFERENCES sessions(session_id),
    ts                      TIMESTAMPTZ NOT NULL,
    lap_number              INT         CHECK (lap_number IS NULL OR lap_number > 0),
    attacker_code           TEXT        NOT NULL,
    defender_code           TEXT        NOT NULL,
    type                    TEXT        NOT NULL CHECK (type IN (
        'UNDERCUT_VIABLE','UNDERCUT_RISK','UNDERCUT_DISABLED_RAIN',
        'SUSPENDED_SC','SUSPENDED_VSC','INSUFFICIENT_DATA'
    )),
    estimated_gain_ms       INT,
    pit_loss_ms             INT,
    gap_actual_ms           INT,
    score                   REAL        CHECK (score IS NULL OR (score >= 0 AND score <= 1)),
    confidence              REAL        CHECK (confidence IS NULL
                                                OR (confidence >= 0 AND confidence <= 1)),
    payload                 JSONB
);
CREATE INDEX idx_alerts_session_ts ON alerts (session_id, ts DESC);
CREATE INDEX idx_alerts_run        ON alerts (run_id);

-- Curated list used by the back-test harness (Stream A, Day 6).
CREATE TABLE known_undercuts (
    session_id              TEXT        NOT NULL REFERENCES sessions(session_id),
    attacker_code           TEXT        NOT NULL,
    defender_code           TEXT        NOT NULL,
    lap_of_attempt          INT         NOT NULL CHECK (lap_of_attempt > 0),
    was_successful          BOOLEAN     NOT NULL,
    notes                   TEXT,
    PRIMARY KEY (session_id, attacker_code, defender_code, lap_of_attempt)
);

-- ----------------------------------------------------------------------------
-- 5. Materialised views
-- ----------------------------------------------------------------------------

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
  AND lap_time_ms BETWEEN 60000 AND 180000;

CREATE INDEX idx_clean_air_session_driver
    ON clean_air_lap_times (session_id, driver_code, lap_number);

-- Refresh after each ingest run:
--   REFRESH MATERIALIZED VIEW clean_air_lap_times;
-- (Switch to CONCURRENTLY once a UNIQUE index is added in a follow-up
-- migration. Refresh is cheap at V1 volumes.)
