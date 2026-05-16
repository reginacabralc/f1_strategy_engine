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

// Normalized shape used by all components. Always produced by normalizeAlertPayload.
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

// Raw shape the backend currently emits (attacker/defender/current_lap).
// Also accepts spec-shaped payloads so the normalizer handles both.
export interface BackendAlertPayload {
  alert_type: AlertType;
  session_id: string;
  score: number;
  confidence: number;
  estimated_gain_ms: number;
  pit_loss_ms: number;
  gap_actual_ms: number;
  // backend-shaped fields
  attacker?: string;
  defender?: string;
  current_lap?: number;
  // spec-shaped fields (may arrive once backend is updated)
  alert_id?: string;
  attacker_code?: string;
  defender_code?: string;
  lap_number?: number;
  ventana_laps?: number;
  predictor_used?: string;
}

// Accepts either backend-shaped or spec-shaped alert payloads and returns a
// fully populated AlertPayload. Generates a deterministic alert_id when absent
// so React keys remain stable across re-renders.
export function normalizeAlertPayload(raw: BackendAlertPayload): AlertPayload {
  const attacker_code = raw.attacker_code ?? raw.attacker ?? "";
  const defender_code = raw.defender_code ?? raw.defender ?? "";
  const lap_number = raw.lap_number ?? raw.current_lap ?? 0;
  const alert_id =
    raw.alert_id ??
    `${raw.session_id}|${raw.alert_type}|${attacker_code}|${defender_code}|${lap_number}|${raw.estimated_gain_ms}|${raw.score}`;
  return {
    alert_id,
    session_id: raw.session_id,
    lap_number,
    alert_type: raw.alert_type,
    attacker_code,
    defender_code,
    estimated_gain_ms: raw.estimated_gain_ms,
    pit_loss_ms: raw.pit_loss_ms,
    gap_actual_ms: raw.gap_actual_ms,
    score: raw.score,
    confidence: raw.confidence,
    ventana_laps: raw.ventana_laps ?? 0,
    predictor_used: raw.predictor_used ?? "",
  };
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
// alert uses BackendAlertPayload (wire shape); useRaceFeed normalizes before state.
type WsMessageMap = {
  snapshot: RaceSnapshot;
  lap_update: LapUpdatePayload;
  pit_stop: PitStopPayload;
  alert: BackendAlertPayload;
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
