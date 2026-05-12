// Hand-written from docs/interfaces/openapi_v1.yaml
// TODO: replace with `openapi-typescript` codegen once spec stabilises

export type PredictorName = "scipy" | "xgboost";

export type Compound = "SOFT" | "MEDIUM" | "HARD" | "INTER" | "WET";

export type TrackStatus =
  | "GREEN"
  | "YELLOW"
  | "SC"
  | "VSC"
  | "RED"
  | "UNKNOWN";

export interface SessionSummary {
  session_id: string;
  circuit_id: string;
  season: number;
  round_number: number;
  date: string;
  total_laps: number | null;
}

export interface DriverState {
  driver_code: string;
  team_code: string | null;
  position: number;
  gap_to_leader_ms: number | null;
  gap_to_ahead_ms: number | null;
  last_lap_ms: number | null;
  compound: Compound;
  tyre_age: number;
  is_in_pit: boolean;
  is_lapped: boolean;
  last_pit_lap: number | null;
  stint_number: number;
  undercut_score: number | null;
}

export interface RaceSnapshot {
  session_id: string;
  current_lap: number;
  track_status: TrackStatus;
  track_temp_c: number | null;
  air_temp_c: number | null;
  humidity_pct: number | null;
  drivers: DriverState[];
  active_predictor: PredictorName;
  last_event_ts: string;
}
