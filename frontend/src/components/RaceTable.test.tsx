import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { RaceTable } from "./RaceTable";

describe("RaceTable", () => {
  it("renders mock driver rows", () => {
    render(<RaceTable />);
    expect(screen.getByText("VER")).toBeInTheDocument();
    expect(screen.getByText("LEC")).toBeInTheDocument();
  });

  it("shows position column header", () => {
    render(<RaceTable />);
    expect(screen.getByText("P")).toBeInTheDocument();
  });
});
