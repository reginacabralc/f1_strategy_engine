import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { DegradationCurve } from "../api/types";

// ResizeObserver is not available in jsdom; Recharts needs it.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

vi.mock("../hooks/useDegradation");

import { DegradationChart } from "./DegradationChart";
import { useDegradation } from "../hooks/useDegradation";

const mockHook = vi.mocked(useDegradation);

const MOCK_CURVE: DegradationCurve = {
  circuit_id: "monaco",
  compound: "MEDIUM",
  coefficients: { a: 74500, b: 120, c: 5 },
  r_squared: 0.36,
  n_samples: 100,
};

describe("DegradationChart", () => {
  beforeEach(() => {
    Object.defineProperty(window, "ResizeObserver", {
      writable: true,
      configurable: true,
      value: ResizeObserverStub,
    });
  });

  it("shows loading indicator while fetching", () => {
    mockHook.mockReturnValue({
      isLoading: true,
      isError: false,
      data: undefined,
    } as ReturnType<typeof useDegradation>);

    render(<DegradationChart circuit="monaco" />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("shows error message when no data is available", () => {
    mockHook.mockReturnValue({
      isLoading: false,
      isError: true,
      data: undefined,
    } as ReturnType<typeof useDegradation>);

    render(<DegradationChart circuit="monaco" />);
    expect(screen.getByTestId("degradation-error")).toBeInTheDocument();
    expect(screen.getByText(/No degradation data/)).toBeInTheDocument();
  });

  it("shows R² and sample count when data is loaded", () => {
    mockHook.mockReturnValue({
      isLoading: false,
      isError: false,
      data: MOCK_CURVE,
    } as ReturnType<typeof useDegradation>);

    render(<DegradationChart circuit="monaco" />);
    expect(screen.getByText(/R²=0\.36/)).toBeInTheDocument();
    expect(screen.getByText(/n=100/)).toBeInTheDocument();
  });

  it("renders compound selector buttons", () => {
    mockHook.mockReturnValue({
      isLoading: false,
      isError: false,
      data: MOCK_CURVE,
    } as ReturnType<typeof useDegradation>);

    render(<DegradationChart />);
    expect(screen.getByRole("button", { name: "SOFT" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "MEDIUM" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "HARD" })).toBeInTheDocument();
  });
});
