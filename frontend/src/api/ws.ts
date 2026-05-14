// WebSocket message envelope and payload types for /ws/v1/live.
// Hand-written against docs/interfaces/websocket_messages.md.
// Shared domain schemas (RaceSnapshot, AlertType, etc.) come from ./types.
//
// If the server adds a new message type, add it to WsMessageMap and a
// corresponding payload interface — then useRaceFeed will handle it
// automatically in the `default` branch until a dedicated case is added.

import type { AlertType, PredictorName, RaceSnapshot, TrackStatus } from "./types";

// ─── Payload types ────────────────────────────────────────────────────────────

// snapshot payload is RaceSnapshot from the OpenAPI spec.
export type { RaceSnapshot };

export interface AlertPayload {
  alert_id: string;
  session_id: string;
  lap_number: number;
  alert_type: AlertType;
  attacker_code: string;
  defender_code: string;
  estimated_gain_ms: number;
  pit_loss_ms: number;
  gap_actual_ms: number;
  score: number;
  confidence: number;
  ventana_laps: number;
  predictor_used: string;
}

export interface LapUpdatePayload {
  session_id: string;
  lap_number: number;
  driver_code: string;
  lap_time_ms: number;
  position: number;
  gap_to_leader_ms: number | null;
  gap_to_ahead_ms: number | null;
  compound: string;
  tyre_age: number;
  is_pit_in: boolean;
  is_pit_out: boolean;
  track_status: TrackStatus;
}

export interface PitStopPayload {
  session_id: string;
  lap_number: number;
  driver_code: string;
  phase: "in" | "out";
  duration_ms?: number;
  new_compound?: string;
}

export interface TrackStatusPayload {
  session_id: string;
  lap_number: number;
  status: TrackStatus;
  previous_status: TrackStatus;
  started: boolean;
}

export interface ReplayStatePayload {
  run_id: string;
  session_id: string;
  state: "started" | "stopped" | "finished";
  speed_factor: number;
  pace_predictor: PredictorName;
}

export interface WsErrorPayload {
  // Known codes listed for autocomplete; spec says the set is extensible.
  code: string;
  message: string;
}

// ─── Envelope ─────────────────────────────────────────────────────────────────

// Mapping of type discriminant → payload shape.
// ping/pong have no payload (undefined at runtime; optional in the type).
type WsMessageMap = {
  snapshot: RaceSnapshot;
  lap_update: LapUpdatePayload;
  pit_stop: PitStopPayload;
  alert: AlertPayload;
  track_status: TrackStatusPayload;
  replay_state: ReplayStatePayload;
  error: WsErrorPayload;
  ping: Record<string, unknown>;
  pong: Record<string, unknown>;
};

export type WsMsgType = keyof WsMessageMap;

// Discriminated union — TypeScript can narrow by `msg.type` in a switch.
export type WsEnvelope = {
  [K in WsMsgType]: {
    type: K;
    ts: string;
    payload?: WsMessageMap[K];
  };
}[WsMsgType];

// ─── Client → server ──────────────────────────────────────────────────────────

export interface WsPongMessage {
  type: "pong";
  ts: string;
}
