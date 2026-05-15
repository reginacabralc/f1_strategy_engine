import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../hooks/usePredictor");

import { PredictorToggle } from "./PredictorToggle";
import { usePredictor } from "../hooks/usePredictor";

const mockHook = vi.mocked(usePredictor);
const mockSwitch = vi.fn();

function idle() {
  mockHook.mockReturnValue({ pendingTarget: null, error: null, switchPredictor: mockSwitch });
}

describe("PredictorToggle", () => {
  beforeEach(() => {
    mockSwitch.mockReset();
    idle();
  });

  it("renders scipy and xgboost buttons", () => {
    render(<PredictorToggle />);
    expect(screen.getByTestId("predictor-scipy")).toBeInTheDocument();
    expect(screen.getByTestId("predictor-xgboost")).toBeInTheDocument();
  });

  it("marks scipy as active by default when no prop given", () => {
    render(<PredictorToggle />);
    expect(screen.getByTestId("predictor-scipy")).toHaveAttribute("aria-checked", "true");
    expect(screen.getByTestId("predictor-xgboost")).toHaveAttribute("aria-checked", "false");
  });

  it("marks activePredictor prop as the active button", () => {
    render(<PredictorToggle activePredictor="xgboost" />);
    expect(screen.getByTestId("predictor-xgboost")).toHaveAttribute("aria-checked", "true");
    expect(screen.getByTestId("predictor-scipy")).toHaveAttribute("aria-checked", "false");
  });

  it("calls switchPredictor with the correct predictor when clicked", () => {
    render(<PredictorToggle activePredictor="scipy" />);
    fireEvent.click(screen.getByTestId("predictor-xgboost"));
    expect(mockSwitch).toHaveBeenCalledOnce();
    expect(mockSwitch).toHaveBeenCalledWith("xgboost");
  });

  it("shows Switching… text while pending", () => {
    mockHook.mockReturnValue({
      pendingTarget: "xgboost",
      error: null,
      switchPredictor: mockSwitch,
    });
    render(<PredictorToggle activePredictor="scipy" />);
    expect(screen.getByText("Switching…")).toBeInTheDocument();
  });

  it("optimistically displays pendingTarget while switching", () => {
    mockHook.mockReturnValue({
      pendingTarget: "xgboost",
      error: null,
      switchPredictor: mockSwitch,
    });
    render(<PredictorToggle activePredictor="scipy" />);
    expect(screen.getByTestId("predictor-xgboost")).toHaveAttribute("aria-checked", "true");
  });

  it("disables both buttons while pending", () => {
    mockHook.mockReturnValue({
      pendingTarget: "xgboost",
      error: null,
      switchPredictor: mockSwitch,
    });
    render(<PredictorToggle activePredictor="scipy" />);
    expect(screen.getByTestId("predictor-scipy")).toBeDisabled();
    expect(screen.getByTestId("predictor-xgboost")).toBeDisabled();
  });

  it("shows error message when error is set", () => {
    mockHook.mockReturnValue({
      pendingTarget: null,
      error: "XGBoost model not available. Staying on scipy.",
      switchPredictor: mockSwitch,
    });
    render(<PredictorToggle activePredictor="scipy" />);
    expect(screen.getByTestId("predictor-error")).toBeInTheDocument();
    expect(screen.getByText(/XGBoost model not available/)).toBeInTheDocument();
  });

  it("reverts to activePredictor display after error clears (pending=false)", () => {
    // When error is set and pending is null, displayed = activePredictor (scipy stays selected)
    mockHook.mockReturnValue({
      pendingTarget: null,
      error: "XGBoost model not available. Staying on scipy.",
      switchPredictor: mockSwitch,
    });
    render(<PredictorToggle activePredictor="scipy" />);
    expect(screen.getByTestId("predictor-scipy")).toHaveAttribute("aria-checked", "true");
    expect(screen.getByTestId("predictor-xgboost")).toHaveAttribute("aria-checked", "false");
  });

  it("does not show error element when no error", () => {
    render(<PredictorToggle activePredictor="scipy" />);
    expect(screen.queryByTestId("predictor-error")).not.toBeInTheDocument();
  });
});
