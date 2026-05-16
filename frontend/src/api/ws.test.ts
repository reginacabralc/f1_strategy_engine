import { describe, it, expect } from "vitest";
import { normalizeAlertPayload } from "./ws";
import type { BackendAlertPayload } from "./ws";

const BACKEND_PAYLOAD: BackendAlertPayload = {
  alert_type: "UNDERCUT_VIABLE",
  attacker: "NOR",
  defender: "VER",
  score: 0.7234,
  confidence: 0.61,
  estimated_gain_ms: 1800,
  pit_loss_ms: 22000,
  gap_actual_ms: 2500,
  session_id: "monaco_2024_R",
  current_lap: 23,
};

const SPEC_PAYLOAD: BackendAlertPayload = {
  alert_id: "alert-abc-123",
  alert_type: "UNDERCUT_VIABLE",
  attacker_code: "LEC",
  defender_code: "HAM",
  score: 0.65,
  confidence: 0.72,
  estimated_gain_ms: 1200,
  pit_loss_ms: 21000,
  gap_actual_ms: 1500,
  session_id: "monaco_2024_R",
  lap_number: 31,
};

describe("normalizeAlertPayload", () => {
  it("maps backend attacker/defender/current_lap to spec fields", () => {
    const result = normalizeAlertPayload(BACKEND_PAYLOAD);
    expect(result.attacker_code).toBe("NOR");
    expect(result.defender_code).toBe("VER");
    expect(result.lap_number).toBe(23);
  });

  it("preserves spec-shaped attacker_code/defender_code/lap_number when present", () => {
    const result = normalizeAlertPayload(SPEC_PAYLOAD);
    expect(result.attacker_code).toBe("LEC");
    expect(result.defender_code).toBe("HAM");
    expect(result.lap_number).toBe(31);
  });

  it("preserves alert_id when provided by spec-shaped payload", () => {
    const result = normalizeAlertPayload(SPEC_PAYLOAD);
    expect(result.alert_id).toBe("alert-abc-123");
  });

  it("generates a stable deterministic alert_id when missing", () => {
    const r1 = normalizeAlertPayload(BACKEND_PAYLOAD);
    const r2 = normalizeAlertPayload(BACKEND_PAYLOAD);
    expect(r1.alert_id).toBe(r2.alert_id);
    expect(r1.alert_id.length).toBeGreaterThan(0);
  });

  it("does not return undefined for attacker_code, defender_code, or lap_number", () => {
    const result = normalizeAlertPayload(BACKEND_PAYLOAD);
    expect(result.attacker_code).not.toBeUndefined();
    expect(result.defender_code).not.toBeUndefined();
    expect(result.lap_number).not.toBeUndefined();
  });

  it("preserves shared fields from backend payload", () => {
    const result = normalizeAlertPayload(BACKEND_PAYLOAD);
    expect(result.alert_type).toBe("UNDERCUT_VIABLE");
    expect(result.score).toBe(0.7234);
    expect(result.confidence).toBe(0.61);
    expect(result.estimated_gain_ms).toBe(1800);
    expect(result.pit_loss_ms).toBe(22000);
    expect(result.gap_actual_ms).toBe(2500);
    expect(result.session_id).toBe("monaco_2024_R");
  });

  it("spec_code fields take precedence over backend fields when both present", () => {
    const mixed: BackendAlertPayload = {
      ...BACKEND_PAYLOAD,
      attacker_code: "HAM",
      defender_code: "LEC",
      lap_number: 99,
    };
    const result = normalizeAlertPayload(mixed);
    expect(result.attacker_code).toBe("HAM");
    expect(result.defender_code).toBe("LEC");
    expect(result.lap_number).toBe(99);
  });
});
