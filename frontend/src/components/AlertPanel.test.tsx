import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { AlertPanel } from "./AlertPanel";
import type { AlertPayload } from "../api/ws";

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
