-- ============================================================================
-- PitWall DB Schema v1
-- ============================================================================
-- Propósito: schema mínimo para el MVP. Acordado en kickoff Día 1.
-- Owner: Stream A (con review de B y D).
-- Cambiar este archivo requiere avisar al equipo (ver AGENTS.md).
-- Las migraciones reales viven en backend/src/pitwall/db/migrations/ (alembic).
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ----------------------------------------------------------------------------
-- Catálogos
-- ----------------------------------------------------------------------------

CREATE TABLE circuits (
    circuit_id              TEXT PRIMARY KEY,           -- 'monaco', 'spa'
    name                    TEXT NOT NULL,
    country                 TEXT,
    pit_lane_loss_seconds   REAL,                       -- referencia teórica
    pit_lane_speed_limit    INT,                        -- km/h
    total_laps_typical      INT
);

CREATE TABLE seasons (
    season                  INT PRIMARY KEY,
    regulations             TEXT                        -- '2022-2025 ground effect'
);

CREATE TABLE events (
    event_id                TEXT PRIMARY KEY,           -- 'monaco_2024'
    season                  INT REFERENCES seasons,
    circuit_id              TEXT REFERENCES circuits,
    round_number            INT NOT NULL,
    name                    TEXT NOT NULL,              -- 'Monaco Grand Prix'
    start_date              DATE
);

CREATE TABLE sessions (
    session_id              TEXT PRIMARY KEY,           -- 'monaco_2024_R'
    event_id                TEXT REFERENCES events,
    session_type            TEXT NOT NULL,              -- 'R', 'Q', 'FP1'...
    date                    DATE NOT NULL,
    total_laps              INT
);

CREATE TABLE teams (
    team_code               TEXT PRIMARY KEY,           -- 'MCL', 'MER'
    full_name               TEXT
);

CREATE TABLE drivers (
    driver_code             TEXT PRIMARY KEY,           -- 'VER', 'HAM'
    full_name               TEXT,
    team_code               TEXT REFERENCES teams,
    season                  INT REFERENCES seasons      -- equipo varía año a año
);

-- ----------------------------------------------------------------------------
-- Time-series (hypertables)
-- ----------------------------------------------------------------------------

CREATE TABLE laps (
    session_id              TEXT NOT NULL REFERENCES sessions,
    driver_code             TEXT NOT NULL REFERENCES drivers,
    lap_number              INT NOT NULL,
    lap_time_ms             INT,
    sector_1_ms             INT,
    sector_2_ms             INT,
    sector_3_ms             INT,
    compound                TEXT,                       -- 'SOFT'/'MEDIUM'/'HARD'/'INTER'/'WET'
    tyre_age                INT,                        -- vueltas en este compuesto
    is_pit_in               BOOLEAN DEFAULT FALSE,
    is_pit_out              BOOLEAN DEFAULT FALSE,
    is_valid                BOOLEAN DEFAULT TRUE,       -- excluye SC/VSC/deleted
    track_status            TEXT,                       -- 'GREEN', 'SC', 'VSC', 'YELLOW', 'RED'
    position                INT,
    gap_to_leader_ms        INT,
    gap_to_ahead_ms         INT,
    ts                      TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (session_id, driver_code, lap_number)
);
SELECT create_hypertable('laps', 'ts', chunk_time_interval => INTERVAL '1 day');
CREATE INDEX idx_laps_session_driver ON laps (session_id, driver_code);

CREATE TABLE pit_stops (
    session_id              TEXT REFERENCES sessions,
    driver_code             TEXT REFERENCES drivers,
    lap_number              INT NOT NULL,
    duration_ms             INT,                        -- tiempo estacionario
    pit_loss_ms             INT,                        -- delta vs vuelta normal
    new_compound            TEXT,
    ts                      TIMESTAMPTZ,
    PRIMARY KEY (session_id, driver_code, lap_number)
);

CREATE TABLE stints (
    session_id              TEXT REFERENCES sessions,
    driver_code             TEXT REFERENCES drivers,
    stint_number            INT NOT NULL,
    compound                TEXT,
    lap_start               INT NOT NULL,
    lap_end                 INT,
    age_at_start            INT DEFAULT 0,
    PRIMARY KEY (session_id, driver_code, stint_number)
);

CREATE TABLE track_status_events (
    session_id              TEXT REFERENCES sessions,
    lap_number              INT,
    status                  TEXT NOT NULL,              -- 'GREEN', 'SC', 'VSC', 'RED', 'YELLOW'
    started_ts              TIMESTAMPTZ NOT NULL,
    ended_ts                TIMESTAMPTZ,
    PRIMARY KEY (session_id, started_ts)
);

CREATE TABLE weather (
    session_id              TEXT REFERENCES sessions,
    lap_number              INT,
    track_temp_c            REAL,
    air_temp_c              REAL,
    humidity                REAL,
    rainfall                BOOLEAN,
    ts                      TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (session_id, ts)
);

-- ----------------------------------------------------------------------------
-- Modelos / coeficientes / agregados
-- ----------------------------------------------------------------------------

CREATE TABLE degradation_coefficients (
    circuit_id              TEXT REFERENCES circuits,
    compound                TEXT,
    a                       REAL,                       -- intercept (ms)
    b                       REAL,                       -- linear (ms/lap)
    c                       REAL,                       -- quadratic (ms/lap²)
    r_squared               REAL,
    n_samples               INT,
    fitted_at               TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (circuit_id, compound)
);

CREATE TABLE pit_loss_estimates (
    circuit_id              TEXT REFERENCES circuits,
    team_code               TEXT REFERENCES teams,
    pit_loss_ms             INT,
    n_samples               INT,
    computed_at             TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (circuit_id, team_code)
);

CREATE TABLE driver_skill_offsets (
    driver_code             TEXT REFERENCES drivers,
    circuit_id              TEXT REFERENCES circuits,
    compound                TEXT,
    offset_ms               REAL,                       -- delta vs predicción base
    n_samples               INT,
    PRIMARY KEY (driver_code, circuit_id, compound)
);

CREATE TABLE model_registry (
    model_id                TEXT PRIMARY KEY,           -- 'xgb_pace_v1'
    model_type              TEXT,                       -- 'xgboost', 'scipy'
    version                 TEXT,
    trained_at              TIMESTAMPTZ DEFAULT NOW(),
    metrics                 JSONB,                      -- {mae_k1: ..., mae_k3: ...}
    features                JSONB,                      -- lista de features usadas
    train_session_ids       TEXT[],
    file_path               TEXT                        -- 'models/xgb_pace_v1.json'
);

-- ----------------------------------------------------------------------------
-- Live / runtime
-- ----------------------------------------------------------------------------

CREATE TABLE replay_runs (
    run_id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id              TEXT REFERENCES sessions,
    speed_factor            REAL NOT NULL,
    started_at              TIMESTAMPTZ DEFAULT NOW(),
    ended_at                TIMESTAMPTZ,
    pace_predictor          TEXT NOT NULL,              -- 'scipy' o 'xgb'
    note                    TEXT
);

CREATE TABLE alerts (
    alert_id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                  UUID REFERENCES replay_runs,
    session_id              TEXT REFERENCES sessions,
    ts                      TIMESTAMPTZ NOT NULL,
    lap_number              INT,
    attacker_code           TEXT,
    defender_code           TEXT,
    type                    TEXT,                       -- 'UNDERCUT_VIABLE', 'UNDERCUT_RISK', 'SUSPENDED_SC', ...
    estimated_gain_ms       INT,
    pit_loss_ms             INT,
    gap_actual_ms           INT,
    score                   REAL,
    confidence              REAL,
    payload                 JSONB
);
SELECT create_hypertable('alerts', 'ts', chunk_time_interval => INTERVAL '1 day');

CREATE TABLE known_undercuts (                          -- lista curada para backtest
    session_id              TEXT REFERENCES sessions,
    attacker_code           TEXT,
    defender_code           TEXT,
    lap_of_attempt          INT NOT NULL,
    was_successful          BOOLEAN NOT NULL,
    notes                   TEXT,
    PRIMARY KEY (session_id, attacker_code, defender_code, lap_of_attempt)
);

-- ----------------------------------------------------------------------------
-- Vistas materializadas
-- ----------------------------------------------------------------------------

CREATE MATERIALIZED VIEW clean_air_lap_times AS
SELECT
    session_id, driver_code, lap_number, lap_time_ms,
    compound, tyre_age, position, ts
FROM laps
WHERE is_valid = TRUE
  AND is_pit_in = FALSE
  AND is_pit_out = FALSE
  AND track_status = 'GREEN'
  AND lap_time_ms BETWEEN 60000 AND 180000;

CREATE INDEX ON clean_air_lap_times (session_id, driver_code, lap_number);

-- Refresh: REFRESH MATERIALIZED VIEW clean_air_lap_times;
-- (Llamar tras cada ingesta nueva.)
