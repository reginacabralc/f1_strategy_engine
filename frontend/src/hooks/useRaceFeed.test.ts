import { describe, it, expect } from "vitest";
import { applyLapUpdate, applyPitStop, applyTrackStatus } from "./useRaceFeed";
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
