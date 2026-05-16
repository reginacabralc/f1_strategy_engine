import { useEffect, useRef, useState } from "react";
import type { Compound, RaceSnapshot } from "../api/types";
import {
  normalizeAlertPayload,
} from "../api/ws";
import type {
  AlertPayload,
  LapUpdatePayload,
  PitStopPayload,
  ReplayStatePayload,
  TrackStatusPayload,
  WsEnvelope,
  WsPongMessage,
} from "../api/ws";

export type ConnectionStatus =
  | "idle"
  | "connecting"
  | "open"
  | "closed"
  | "reconnecting"
  | "error";

const INITIAL_BACKOFF_MS = 1_000;
const MAX_BACKOFF_MS = 16_000;
const MAX_ALERTS = 20;

// ─── Pure helpers (exported for unit tests) ───────────────────────────────────

const COMPOUNDS = new Set<string>(["SOFT", "MEDIUM", "HARD", "INTER", "WET"]);
function isCompound(s: string): s is Compound {
  return COMPOUNDS.has(s);
}

export function applyLapUpdate(
  snapshot: RaceSnapshot,
  payload: LapUpdatePayload,
): RaceSnapshot {
  const drivers = snapshot.drivers.map((d) => {
    if (d.driver_code !== payload.driver_code) return d;
    return {
      ...d,
      position: payload.position,
      gap_to_leader_ms: payload.gap_to_leader_ms,
      gap_to_ahead_ms: payload.gap_to_ahead_ms,
      last_lap_ms: payload.lap_time_ms,
      compound: isCompound(payload.compound) ? payload.compound : d.compound,
      tyre_age: payload.tyre_age,
      is_in_pit: payload.is_pit_in,
    };
  });
  const sorted = [...drivers].sort((a, b) => a.position - b.position);
  return { ...snapshot, current_lap: payload.lap_number, drivers: sorted };
}

export function applyPitStop(
  snapshot: RaceSnapshot,
  payload: PitStopPayload,
): RaceSnapshot {
  const drivers = snapshot.drivers.map((d) => {
    if (d.driver_code !== payload.driver_code) return d;
    if (payload.phase === "in") {
      return { ...d, is_in_pit: true, last_pit_lap: payload.lap_number };
    }
    return {
      ...d,
      is_in_pit: false,
      compound:
        payload.new_compound && isCompound(payload.new_compound)
          ? payload.new_compound
          : d.compound,
    };
  });
  return { ...snapshot, drivers };
}

export function applyTrackStatus(
  snapshot: RaceSnapshot,
  payload: TrackStatusPayload,
): RaceSnapshot {
  return {
    ...snapshot,
    track_status: payload.status,
    current_lap: payload.lap_number,
  };
}

function getWsUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/v1/live`;
}

export function useRaceFeed() {
  const socketRef = useRef<WebSocket | null>(null);
  const backoffRef = useRef<number>(INITIAL_BACKOFF_MS);
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const [status, setStatus] = useState<ConnectionStatus>("idle");
  const [snapshot, setSnapshot] = useState<RaceSnapshot | null>(null);
  const [alerts, setAlerts] = useState<AlertPayload[]>([]);
  const [replayState, setReplayState] = useState<ReplayStatePayload | null>(null);
  const [lastMessage, setLastMessage] = useState<WsEnvelope | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    function connect(): void {
      if (cancelled) return;

      setStatus("connecting");
      const ws = new WebSocket(getWsUrl());
      socketRef.current = ws;

      ws.onopen = () => {
        if (cancelled) {
          ws.onopen = ws.onmessage = ws.onerror = ws.onclose = null;
          ws.close();
          return;
        }
        backoffRef.current = INITIAL_BACKOFF_MS;
        setStatus("open");
        setError(null);
      };

      ws.onmessage = (event: MessageEvent) => {
        if (cancelled) return;
        let msg: WsEnvelope;
        try {
          msg = JSON.parse(event.data as string) as WsEnvelope;
        } catch {
          return;
        }
        setLastMessage(msg);
        switch (msg.type) {
          // ── Backend V1 emitted types ───────────────────────────────────────
          case "snapshot":
            if (msg.payload) setSnapshot(msg.payload);
            break;
          case "alert":
            if (msg.payload) {
              setAlerts((prev) =>
                [normalizeAlertPayload(msg.payload!), ...prev].slice(0, MAX_ALERTS),
              );
            }
            break;
          case "replay_state":
            if (msg.payload) setReplayState(msg.payload);
            break;
          case "ping": {
            const pong: WsPongMessage = { type: "pong", ts: new Date().toISOString() };
            ws.send(JSON.stringify(pong));
            break;
          }
          // ── Spec-defined; not emitted by backend V1 ───────────────────────
          // V1 engine broadcasts a full snapshot on each lap_complete instead.
          case "lap_update":
            if (msg.payload)
              setSnapshot((prev) =>
                prev ? applyLapUpdate(prev, msg.payload!) : prev,
              );
            break;
          // Pit information flows through snapshot.drivers[].is_in_pit in V1.
          case "pit_stop":
            if (msg.payload)
              setSnapshot((prev) =>
                prev ? applyPitStop(prev, msg.payload!) : prev,
              );
            break;
          // SC/VSC arrives as a SUSPENDED_SC/SUSPENDED_VSC alert type in V1.
          case "track_status":
            if (msg.payload)
              setSnapshot((prev) =>
                prev ? applyTrackStatus(prev, msg.payload!) : prev,
              );
            break;
          // V1 backend disconnects on error rather than sending an error frame.
          case "error":
            if (msg.payload) setError(msg.payload.message);
            break;
          default:
            break;
        }
      };

      ws.onerror = () => {
        if (cancelled) return;
        setStatus("error");
        setError("WebSocket error");
      };

      ws.onclose = () => {
        if (cancelled) return;
        socketRef.current = null;
        setStatus("reconnecting");
        const delay = backoffRef.current;
        backoffRef.current = Math.min(delay * 2, MAX_BACKOFF_MS);
        timerRef.current = setTimeout(connect, delay);
      };
    }

    connect();

    return () => {
      cancelled = true;
      clearTimeout(timerRef.current);
      const ws = socketRef.current;
      if (ws) {
        ws.onopen = null;
        ws.onmessage = null;
        ws.onerror = null;
        ws.onclose = null;
        ws.close();
        socketRef.current = null;
      }
    };
  }, []);

  return { status, snapshot, alerts, replayState, lastMessage, error };
}
