import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { applyLapUpdate, applyPitStop, applyTrackStatus, useRaceFeed } from "./useRaceFeed";
import type { RaceSnapshot } from "../api/types";
import type { LapUpdatePayload, PitStopPayload, TrackStatusPayload } from "../api/ws";

const BASE_SNAPSHOT: RaceSnapshot = {
  session_id: "monaco_2024_R",
  current_lap: 10,
  track_status: "GREEN",
  drivers: [
    {
      driver_code: "VER",
      team_code: "RBR",
      position: 1,
      gap_to_leader_ms: 0,
      gap_to_ahead_ms: null,
      last_lap_ms: 74200,
      compound: "MEDIUM",
      tyre_age: 10,
      is_in_pit: false,
      is_lapped: false,
      last_pit_lap: null,
      stint_number: 1,
      undercut_score: null,
    },
    {
      driver_code: "LEC",
      team_code: "FER",
      position: 2,
      gap_to_leader_ms: 2500,
      gap_to_ahead_ms: 2500,
      last_lap_ms: 74400,
      compound: "MEDIUM",
      tyre_age: 10,
      is_in_pit: false,
      is_lapped: false,
      last_pit_lap: null,
      stint_number: 1,
      undercut_score: 0.45,
    },
  ],
  active_predictor: "scipy",
  last_event_ts: "2024-05-26T14:10:00Z",
};

describe("applyLapUpdate", () => {
  it("updates matching driver fields and re-sorts by position", () => {
    const payload: LapUpdatePayload = {
      session_id: "monaco_2024_R",
      lap_number: 11,
      driver_code: "LEC",
      lap_time_ms: 74100,
      position: 2,
      gap_to_leader_ms: 1500,
      gap_to_ahead_ms: 1500,
      compound: "HARD",
      tyre_age: 11,
      is_pit_in: false,
      is_pit_out: false,
      track_status: "GREEN",
    };

    const next = applyLapUpdate(BASE_SNAPSHOT, payload);
    const lec = next.drivers.find((d) => d.driver_code === "LEC")!;
    expect(lec.position).toBe(2);
    expect(lec.compound).toBe("HARD");
    expect(lec.tyre_age).toBe(11);
    expect(lec.last_lap_ms).toBe(74100);
    expect(next.current_lap).toBe(11);
    expect(next.drivers[0].driver_code).toBe("VER");
    expect(next.drivers[1].driver_code).toBe("LEC");
  });

  it("ignores unknown driver_code", () => {
    const payload: LapUpdatePayload = {
      session_id: "monaco_2024_R",
      lap_number: 11,
      driver_code: "HAM",
      lap_time_ms: 74000,
      position: 3,
      gap_to_leader_ms: 5000,
      gap_to_ahead_ms: 2500,
      compound: "SOFT",
      tyre_age: 5,
      is_pit_in: false,
      is_pit_out: false,
      track_status: "GREEN",
    };

    const next = applyLapUpdate(BASE_SNAPSHOT, payload);
    expect(next.drivers).toHaveLength(2);
  });

  it("falls back to existing compound when string is not a valid Compound", () => {
    const payload: LapUpdatePayload = {
      session_id: "monaco_2024_R",
      lap_number: 11,
      driver_code: "VER",
      lap_time_ms: 74000,
      position: 1,
      gap_to_leader_ms: 0,
      gap_to_ahead_ms: null,
      compound: "UNKNOWN_TYRE",
      tyre_age: 11,
      is_pit_in: false,
      is_pit_out: false,
      track_status: "GREEN",
    };

    const next = applyLapUpdate(BASE_SNAPSHOT, payload);
    const ver = next.drivers.find((d) => d.driver_code === "VER")!;
    expect(ver.compound).toBe("MEDIUM");
  });
});

describe("applyPitStop", () => {
  it("sets is_in_pit true and records last_pit_lap on phase=in", () => {
    const payload: PitStopPayload = {
      session_id: "monaco_2024_R",
      lap_number: 11,
      driver_code: "VER",
      phase: "in",
    };

    const next = applyPitStop(BASE_SNAPSHOT, payload);
    const ver = next.drivers.find((d) => d.driver_code === "VER")!;
    expect(ver.is_in_pit).toBe(true);
    expect(ver.last_pit_lap).toBe(11);
  });

  it("clears is_in_pit and updates compound on phase=out", () => {
    const inPitSnapshot: RaceSnapshot = {
      ...BASE_SNAPSHOT,
      drivers: BASE_SNAPSHOT.drivers.map((d) =>
        d.driver_code === "VER" ? { ...d, is_in_pit: true } : d,
      ),
    };
    const payload: PitStopPayload = {
      session_id: "monaco_2024_R",
      lap_number: 12,
      driver_code: "VER",
      phase: "out",
      new_compound: "HARD",
    };

    const next = applyPitStop(inPitSnapshot, payload);
    const ver = next.drivers.find((d) => d.driver_code === "VER")!;
    expect(ver.is_in_pit).toBe(false);
    expect(ver.compound).toBe("HARD");
  });
});

describe("applyTrackStatus", () => {
  it("updates track_status and current_lap", () => {
    const payload: TrackStatusPayload = {
      session_id: "monaco_2024_R",
      lap_number: 12,
      status: "SC",
      previous_status: "GREEN",
      started: true,
    };

    const next = applyTrackStatus(BASE_SNAPSHOT, payload);
    expect(next.track_status).toBe("SC");
    expect(next.current_lap).toBe(12);
  });
});

// ─── V1 WebSocket contract — hook observable behaviour ────────────────────────
//
// Backend V1 emits:  snapshot | alert | replay_state | ping
// Not emitted V1:    lap_update | pit_stop | track_status | error
// (see docs/stream-c-phase0-contract-audit.md §2 and ws.ts WsMessageMap)

type FakeWs = {
  onopen: ((e: Event) => void) | null;
  onmessage: ((e: MessageEvent) => void) | null;
  onerror: ((e: Event) => void) | null;
  onclose: ((e: CloseEvent) => void) | null;
  send: ReturnType<typeof vi.fn>;
  close: ReturnType<typeof vi.fn>;
};

describe("useRaceFeed — V1 WebSocket contract", () => {
  let fakeWs: FakeWs | null = null;

  beforeEach(() => {
    fakeWs = null;
    vi.stubGlobal(
      "WebSocket",
      vi.fn().mockImplementation(() => {
        fakeWs = {
          onopen: null,
          onmessage: null,
          onerror: null,
          onclose: null,
          send: vi.fn(),
          close: vi.fn(),
        };
        return fakeWs;
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function open() {
    act(() => {
      fakeWs!.onopen?.(new Event("open"));
    });
  }

  function push(msg: unknown) {
    act(() => {
      fakeWs!.onmessage?.(
        new MessageEvent("message", { data: JSON.stringify(msg) }),
      );
    });
  }

  it("snapshot message replaces snapshot state", () => {
    const { result } = renderHook(() => useRaceFeed());
    open();

    push({ type: "snapshot", ts: "2024-05-26T13:45:21Z", payload: BASE_SNAPSHOT });

    expect(result.current.snapshot).toEqual(BASE_SNAPSHOT);
    expect(result.current.alerts).toHaveLength(0);
    expect(result.current.replayState).toBeNull();
  });

  it("alert message is normalized via normalizeAlertPayload and prepended to alerts", () => {
    const { result } = renderHook(() => useRaceFeed());
    open();

    push({
      type: "alert",
      ts: "2024-05-26T13:46:10Z",
      payload: {
        alert_type: "UNDERCUT_VIABLE",
        attacker: "NOR",
        defender: "VER",
        score: 0.72,
        confidence: 0.61,
        estimated_gain_ms: 1800,
        pit_loss_ms: 22000,
        gap_actual_ms: 2500,
        session_id: "monaco_2024_R",
        current_lap: 23,
      },
    });

    expect(result.current.alerts).toHaveLength(1);
    const alert = result.current.alerts[0];
    expect(alert.attacker_code).toBe("NOR");
    expect(alert.defender_code).toBe("VER");
    expect(alert.lap_number).toBe(23);
    expect(result.current.snapshot).toBeNull();
  });

  it("second alert is prepended so newest alert is first", () => {
    const { result } = renderHook(() => useRaceFeed());
    open();

    const base = {
      alert_type: "UNDERCUT_VIABLE" as const,
      score: 0.7,
      confidence: 0.6,
      estimated_gain_ms: 1800,
      pit_loss_ms: 22000,
      gap_actual_ms: 2500,
      session_id: "monaco_2024_R",
    };

    push({ type: "alert", ts: "T1", payload: { ...base, attacker: "NOR", defender: "VER", current_lap: 10 } });
    push({ type: "alert", ts: "T2", payload: { ...base, attacker: "LEC", defender: "HAM", current_lap: 11 } });

    expect(result.current.alerts).toHaveLength(2);
    expect(result.current.alerts[0].attacker_code).toBe("LEC");
    expect(result.current.alerts[1].attacker_code).toBe("NOR");
  });

  it("replay_state message updates replayState", () => {
    const { result } = renderHook(() => useRaceFeed());
    open();

    push({
      type: "replay_state",
      ts: "2024-05-26T13:00:00Z",
      payload: {
        run_id: "run-abc",
        session_id: "monaco_2024_R",
        state: "started",
        speed_factor: 30,
        pace_predictor: "scipy",
      },
    });

    expect(result.current.replayState?.state).toBe("started");
    expect(result.current.replayState?.speed_factor).toBe(30);
    expect(result.current.replayState?.run_id).toBe("run-abc");
    expect(result.current.snapshot).toBeNull();
    expect(result.current.alerts).toHaveLength(0);
  });

  it("ping message sends pong without mutating snapshot or alerts", () => {
    const { result } = renderHook(() => useRaceFeed());
    open();

    push({ type: "snapshot", ts: "2024-05-26T13:45:21Z", payload: BASE_SNAPSHOT });
    const snapBefore = result.current.snapshot;

    push({ type: "ping", ts: "2024-05-26T13:45:36Z" });

    expect(result.current.snapshot).toBe(snapBefore);
    expect(result.current.alerts).toHaveLength(0);
    expect(fakeWs!.send).toHaveBeenCalledOnce();
    const sent = JSON.parse(fakeWs!.send.mock.calls[0][0] as string) as { type: string };
    expect(sent.type).toBe("pong");
  });

  it("unknown message type is silently ignored", () => {
    const { result } = renderHook(() => useRaceFeed());
    open();

    push({ type: "future_unknown_type", ts: "2024-05-26T13:00:00Z", payload: {} });

    expect(result.current.snapshot).toBeNull();
    expect(result.current.alerts).toHaveLength(0);
    expect(result.current.replayState).toBeNull();
  });

  it("malformed JSON is silently ignored", () => {
    const { result } = renderHook(() => useRaceFeed());
    open();

    act(() => {
      fakeWs!.onmessage?.(new MessageEvent("message", { data: "not-json{{" }));
    });

    expect(result.current.snapshot).toBeNull();
    expect(result.current.alerts).toHaveLength(0);
  });
});
