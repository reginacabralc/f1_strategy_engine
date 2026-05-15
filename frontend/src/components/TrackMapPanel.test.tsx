import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { TrackMapPanel } from "./TrackMapPanel";

describe("TrackMapPanel", () => {
  it("shows the static circuit preview badge", () => {
    render(<TrackMapPanel />);
    expect(screen.getByText("Static circuit preview")).toBeInTheDocument();
  });

  it("shows the V1 unavailability note in the footer", () => {
    render(<TrackMapPanel />);
    expect(
      screen.getByText(/live car coordinates unavailable in V1/i),
    ).toBeInTheDocument();
  });

  it("renders driver markers for the default mock positions", () => {
    render(<TrackMapPanel />);
    expect(screen.getByLabelText(/VER car/)).toBeInTheDocument();
    expect(screen.getByLabelText(/NOR car/)).toBeInTheDocument();
  });
});
