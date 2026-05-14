import { useEffect, useRef, useState } from "react";
import type { RaceSnapshot } from "../api/types";
import type { AlertPayload, ReplayStatePayload, WsEnvelope, WsPongMessage } from "../api/ws";

export type ConnectionStatus =
  | "idle"
  | "connecting"
  | "open"
  | "closed"
  | "reconnecting"
  | "error";

const INITIAL_BACKOFF_MS = 1_000;
const MAX_BACKOFF_MS = 16_000;
const MAX_ALERTS = 50;

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
          case "snapshot":
            if (msg.payload) setSnapshot(msg.payload);
            break;
          case "alert":
            if (msg.payload) {
              setAlerts((prev) => [msg.payload!, ...prev].slice(0, MAX_ALERTS));
            }
            break;
          case "replay_state":
            if (msg.payload) setReplayState(msg.payload);
            break;
          case "error":
            if (msg.payload) setError(msg.payload.message);
            break;
          case "ping": {
            const pong: WsPongMessage = { type: "pong", ts: new Date().toISOString() };
            ws.send(JSON.stringify(pong));
            break;
          }
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
