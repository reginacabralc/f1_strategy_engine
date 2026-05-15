import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { RaceTable } from "./RaceTable";
import type { DriverState } from "../api/types";

const BASE_DRIVER: DriverState = {
  driver_code: "TST",
  team_code: "TST",
  position: 1,
  gap_to_leader_ms: 0,
  gap_to_ahead_ms: null,
  last_lap_ms: 90000,
  compound: "MEDIUM",
  tyre_age: 10,
  is_in_pit: false,
  is_lapped: false,
  last_pit_lap: null,
  stint_number: 1,
  undercut_score: 0.5,
};

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

  it("shows predictor badge when activePredictor prop is provided", () => {
    render(<RaceTable activePredictor="scipy" />);
    expect(screen.getByTestId("predictor-badge")).toBeInTheDocument();
    expect(screen.getByText("scipy")).toBeInTheDocument();
  });

  it("shows xgboost predictor badge correctly", () => {
    render(<RaceTable activePredictor="xgboost" />);
    expect(screen.getByTestId("predictor-badge")).toBeInTheDocument();
    expect(screen.getByText("xgboost")).toBeInTheDocument();
  });

  it("does not show predictor badge when activePredictor is not provided", () => {
    render(<RaceTable />);
    expect(screen.queryByTestId("predictor-badge")).not.toBeInTheDocument();
  });

  describe("ScoreBar", () => {
    it("renders low score (< 0.35) with green styling", () => {
      render(<RaceTable drivers={[{ ...BASE_DRIVER, undercut_score: 0.1 }]} />);
      const pct = screen.getByText("10%");
      expect(pct).toBeInTheDocument();
      expect(pct.className).toContain("text-pitwall-green");
    });

    it("renders mid score (0.35–0.65) with yellow styling", () => {
      render(<RaceTable drivers={[{ ...BASE_DRIVER, undercut_score: 0.5 }]} />);
      const pct = screen.getByText("50%");
      expect(pct).toBeInTheDocument();
      expect(pct.className).toContain("text-pitwall-yellow");
    });

    it("renders high score (≥ 0.65) with accent (red) styling", () => {
      render(<RaceTable drivers={[{ ...BASE_DRIVER, undercut_score: 0.8 }]} />);
      const pct = screen.getByText("80%");
      expect(pct).toBeInTheDocument();
      expect(pct.className).toContain("text-pitwall-accent");
    });

    it("renders dash for null undercut_score", () => {
      render(<RaceTable drivers={[{ ...BASE_DRIVER, undercut_score: null }]} />);
      // Gap column also shows "—" (td); score dash renders as a span
      const scoreSpan = screen
        .getAllByText("—")
        .find((el) => el.tagName === "SPAN");
      expect(scoreSpan).toBeTruthy();
      expect(scoreSpan!.className).toContain("text-pitwall-muted");
    });

    it("clamps score above 1 to 100% with accent styling", () => {
      render(<RaceTable drivers={[{ ...BASE_DRIVER, undercut_score: 1.5 }]} />);
      const pct = screen.getByText("100%");
      expect(pct).toBeInTheDocument();
      expect(pct.className).toContain("text-pitwall-accent");
    });

    it("renders score at exact threshold 0.65 as high (accent)", () => {
      render(<RaceTable drivers={[{ ...BASE_DRIVER, undercut_score: 0.65 }]} />);
      const pct = screen.getByText("65%");
      expect(pct).toBeInTheDocument();
      expect(pct.className).toContain("text-pitwall-accent");
    });
  });
});
