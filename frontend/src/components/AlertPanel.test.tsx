import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { AlertPanel } from "./AlertPanel";
import { normalizeAlertPayload } from "../api/ws";
import type { AlertPayload, BackendAlertPayload } from "../api/ws";

const MOCK_ALERT: AlertPayload = {
  alert_id: "a1",
  session_id: "monaco_2024_R",
  lap_number: 27,
  alert_type: "UNDERCUT_VIABLE",
  attacker_code: "LEC",
  defender_code: "VER",
  estimated_gain_ms: 2100,
  pit_loss_ms: 22000,
  gap_actual_ms: 1800,
  score: 0.82,
  confidence: 0.75,
  ventana_laps: 3,
  predictor_used: "scipy",
};

describe("AlertPanel", () => {
  it("shows empty state when no alerts", () => {
    render(<AlertPanel alerts={[]} />);
    expect(screen.getByTestId("alert-empty")).toBeInTheDocument();
    expect(screen.getByText(/No alerts/)).toBeInTheDocument();
  });

  it("shows empty state with default prop (no alerts passed)", () => {
    render(<AlertPanel />);
    expect(screen.getByTestId("alert-empty")).toBeInTheDocument();
  });

  it("renders attacker and defender codes", () => {
    render(<AlertPanel alerts={[MOCK_ALERT]} />);
    expect(screen.getByText("LEC")).toBeInTheDocument();
    expect(screen.getByText("VER")).toBeInTheDocument();
  });

  it("renders lap number", () => {
    render(<AlertPanel alerts={[MOCK_ALERT]} />);
    expect(screen.getByText("L27")).toBeInTheDocument();
  });

  it("shows CRITICAL badge for UNDERCUT_VIABLE", () => {
    render(<AlertPanel alerts={[MOCK_ALERT]} />);
    expect(screen.getByText("CRITICAL")).toBeInTheDocument();
  });

  it("shows WARN badge for UNDERCUT_RISK", () => {
    const warnAlert: AlertPayload = { ...MOCK_ALERT, alert_id: "a2", alert_type: "UNDERCUT_RISK" };
    render(<AlertPanel alerts={[warnAlert]} />);
    expect(screen.getByText("WARN")).toBeInTheDocument();
  });

  it("shows alert count in header", () => {
    render(<AlertPanel alerts={[MOCK_ALERT]} />);
    expect(screen.getByText("1 active")).toBeInTheDocument();
  });

  it("renders score and confidence", () => {
    render(<AlertPanel alerts={[MOCK_ALERT]} />);
    expect(screen.getByText(/score 82%/)).toBeInTheDocument();
    expect(screen.getByText(/conf 75%/)).toBeInTheDocument();
  });
});

describe("AlertPanel with backend-shaped payloads (via normalizeAlertPayload)", () => {
  it("renders NOR, VER, and L23 from backend attacker/defender/current_lap fields", () => {
    const backendAlert: BackendAlertPayload = {
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
    render(<AlertPanel alerts={[normalizeAlertPayload(backendAlert)]} />);
    expect(screen.getByText("NOR")).toBeInTheDocument();
    expect(screen.getByText("VER")).toBeInTheDocument();
    expect(screen.getByText("L23")).toBeInTheDocument();
  });

  it("renders LEC, HAM, and L31 from spec attacker_code/defender_code/lap_number fields", () => {
    const specAlert: BackendAlertPayload = {
      alert_id: "alert-123",
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
    render(<AlertPanel alerts={[normalizeAlertPayload(specAlert)]} />);
    expect(screen.getByText("LEC")).toBeInTheDocument();
    expect(screen.getByText("HAM")).toBeInTheDocument();
    expect(screen.getByText("L31")).toBeInTheDocument();
  });

  it("uses a stable key (alert_id) for backend payloads with no alert_id", () => {
    const backendAlert: BackendAlertPayload = {
      alert_type: "UNDERCUT_RISK",
      attacker: "SAI",
      defender: "PER",
      score: 0.55,
      confidence: 0.48,
      estimated_gain_ms: 900,
      pit_loss_ms: 21500,
      gap_actual_ms: 1100,
      session_id: "monaco_2024_R",
      current_lap: 40,
    };
    const n1 = normalizeAlertPayload(backendAlert);
    const n2 = normalizeAlertPayload(backendAlert);
    expect(n1.alert_id).toBe(n2.alert_id);
    render(<AlertPanel alerts={[n1]} />);
    expect(screen.getByText("SAI")).toBeInTheDocument();
  });
});

describe("AlertPanel predictor badges", () => {
  it("renders a predictor badge for each predictor type", () => {
    const alerts: AlertPayload[] = [
      { ...MOCK_ALERT, alert_id: "id1", predictor_used: "scipy" },
      { ...MOCK_ALERT, alert_id: "id2", predictor_used: "xgboost" },
      { ...MOCK_ALERT, alert_id: "id3", predictor_used: "causal" },
    ];
    render(<AlertPanel alerts={alerts} />);
    expect(screen.getByTestId("predictor-badge-scipy")).toBeInTheDocument();
    expect(screen.getByTestId("predictor-badge-xgboost")).toBeInTheDocument();
    expect(screen.getByTestId("predictor-badge-causal")).toBeInTheDocument();
  });

  it("does not render a predictor badge when predictor_used is empty string", () => {
    const alert: AlertPayload = { ...MOCK_ALERT, alert_id: "id4", predictor_used: "" };
    render(<AlertPanel alerts={[alert]} />);
    expect(screen.queryByTestId("predictor-badge-")).not.toBeInTheDocument();
  });
});
