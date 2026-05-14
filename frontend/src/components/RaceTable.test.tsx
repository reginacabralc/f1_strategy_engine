import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { RaceTable } from "./RaceTable";
import type { DriverState } from "../api/types";

const LIVE_DRIVERS: DriverState[] = [
  {
    driver_code: "SAI",
    team_code: "FER",
    position: 1,
    gap_to_leader_ms: 0,
    gap_to_ahead_ms: null,
    last_lap_ms: 74200,
    compound: "HARD",
    tyre_age: 15,
    is_in_pit: false,
    is_lapped: false,
    last_pit_lap: 10,
    stint_number: 2,
    undercut_score: 0.1,
  },
];

describe("RaceTable", () => {
  const expectedHeaders = [
    "P",
    "Driver",
    "Team",
    "Gap",
    "Compound",
    "Tyre Age",
    "Score",
  ];

  it("renders mock driver rows", () => {
    render(<RaceTable />);
    expect(screen.getByText("VER")).toBeInTheDocument();
    expect(screen.getByText("LEC")).toBeInTheDocument();
  });

  it("renders the Day 3 race order columns", () => {
    render(<RaceTable />);
    for (const header of expectedHeaders) {
      expect(
        screen.getByRole("columnheader", { name: header }),
      ).toBeInTheDocument();
    }
  });

  it("renders compound, tyre age, and score from the JSON mock", () => {
    render(<RaceTable />);
    expect(screen.getAllByText("MEDIUM")).toHaveLength(2);
    expect(screen.getByText("14")).toBeInTheDocument();
    expect(screen.getByText("72%")).toBeInTheDocument();
  });

  it("uses a horizontally scrollable wrapper for small screens", () => {
    render(<RaceTable />);
    expect(screen.getByTestId("race-table-scroll")).toHaveClass(
      "overflow-x-auto",
    );
  });

  it("renders live driver data when drivers prop is provided", () => {
    render(<RaceTable drivers={LIVE_DRIVERS} isLive connectionStatus="open" />);
    expect(screen.getByText("SAI")).toBeInTheDocument();
    expect(screen.getByText("HARD")).toBeInTheDocument();
  });

  it("shows empty state when drivers array is empty", () => {
    render(<RaceTable drivers={[]} />);
    expect(screen.getByTestId("race-table-empty")).toBeInTheDocument();
  });
});
