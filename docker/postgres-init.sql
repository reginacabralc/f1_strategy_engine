-- Runs once on first container start (empty data directory only).
-- Migration 0001 also creates these with IF NOT EXISTS, so this is
-- belt-and-suspenders for environments that connect before migrations run.
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
