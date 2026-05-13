import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { RaceTable } from "./RaceTable";

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
});
