import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import type { DriverState } from "../api/types";
import { TrackMapPanel } from "./TrackMapPanel";

function makeDriver(overrides: Partial<DriverState> = {}): DriverState {
  return {
    driver_code: "VER",
    team_code: "red_bull",
    position: 1,
    gap_to_leader_ms: 0,
    gap_to_ahead_ms: null,
    last_lap_ms: 95_000,
    compound: "MEDIUM",
    tyre_age: 10,
    is_in_pit: false,
    is_lapped: false,
    last_pit_lap: null,
    stint_number: 1,
    undercut_score: null,
    ...overrides,
  };
}

describe("TrackMapPanel", () => {
  it("renders the panel header with circuit label and Idle badge by default", () => {
    render(<TrackMapPanel circuit="monaco" />);
    expect(screen.getByText("Track Map")).toBeInTheDocument();
    expect(screen.getByText(/Circuit de Monaco/)).toBeInTheDocument();
    expect(screen.getByText("Idle")).toBeInTheDocument();
  });

  it("uses the Bahrain layout when circuit=bahrain", () => {
    render(<TrackMapPanel circuit="bahrain" />);
    expect(
      screen.getByText(/Bahrain International Circuit/),
    ).toBeInTheDocument();
    expect(screen.getByTestId("track-map-bahrain")).toBeInTheDocument();
  });

  it("uses the Monza layout when circuit=monza", () => {
    render(<TrackMapPanel circuit="monza" />);
    expect(
      screen.getByText(/Autodromo Nazionale Monza/),
    ).toBeInTheDocument();
    expect(screen.getByTestId("track-map-monza")).toBeInTheDocument();
  });

  it("resolves the italian alias to Monza", () => {
    render(<TrackMapPanel circuit="italian" />);
    expect(screen.getByTestId("track-map-monza")).toBeInTheDocument();
  });

  it("resolves the british alias to Silverstone", () => {
    render(<TrackMapPanel circuit="british" />);
    expect(screen.getByTestId("track-map-silverstone")).toBeInTheDocument();
  });

  it("shows the fallback note when the circuit is unknown", () => {
    render(<TrackMapPanel circuit="not_a_real_circuit" />);
    expect(
      screen.getByTestId("track-map-fallback-note"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("track-map-generic")).toBeInTheDocument();
  });

  it("does NOT show the fallback note for a supported circuit", () => {
    render(<TrackMapPanel circuit="monaco" />);
    expect(
      screen.queryByTestId("track-map-fallback-note"),
    ).not.toBeInTheDocument();
  });

  it("shows the Live badge when isLive is true", () => {
    render(<TrackMapPanel circuit="monaco" isLive />);
    expect(screen.getByText("Live")).toBeInTheDocument();
  });

  it("displays current lap when provided", () => {
    render(
      <TrackMapPanel circuit="monaco" currentLap={18} totalLaps={78} isLive />,
    );
    expect(screen.getByText(/Lap 18 \/ 78/)).toBeInTheDocument();
  });

  it("falls back to the waiting state when path measurement is unavailable (jsdom)", () => {
    // jsdom does not implement SVGPathElement.getTotalLength, so the live
    // positions cannot be computed in the test runner. The component must
    // degrade gracefully to the empty state rather than crashing.
    const drivers = [
      makeDriver({ driver_code: "VER", position: 1 }),
      makeDriver({
        driver_code: "NOR",
        position: 2,
        team_code: "mclaren",
        gap_to_leader_ms: 1_500,
      }),
    ];
    render(<TrackMapPanel circuit="monaco" drivers={drivers} isLive />);
    expect(
      screen.getByText(/Waiting for replay snapshot/i),
    ).toBeInTheDocument();
  });
});
