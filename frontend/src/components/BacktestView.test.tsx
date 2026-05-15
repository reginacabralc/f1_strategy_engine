import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../hooks/useBacktest");

import { BacktestView } from "./BacktestView";
import { useBacktest } from "../hooks/useBacktest";
import type { BacktestResult } from "../api/types";

const mockHook = vi.mocked(useBacktest);

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const SCIPY_RESULT: BacktestResult = {
  session_id: "monaco_2024_R",
  predictor: "scipy",
  precision: 0.75,
  recall: 0.6,
  f1: 0.67,
  mean_lead_time_laps: 2.5,
  mae_k1_ms: 1200,
  mae_k3_ms: 980,
  mae_k5_ms: 850,
  true_positives: [
    { attacker: "NOR", defender: "VER", lap_alerted: 23, lap_actual: 25, was_successful: true },
    { attacker: "LEC", defender: "HAM", lap_alerted: 31, lap_actual: 32, was_successful: true },
  ],
  false_positives: [
    { attacker: "PIA", defender: "ALO", lap_alerted: 18, lap_actual: null, was_successful: false },
  ],
  false_negatives: [
    { attacker: "SAI", defender: "RUS", lap_alerted: null, lap_actual: 44, was_successful: true },
  ],
};

const XGB_RESULT: BacktestResult = {
  session_id: "monaco_2024_R",
  predictor: "xgboost",
  precision: 0.8,
  recall: 0.65,
  f1: 0.72,
  mean_lead_time_laps: 3.0,
  true_positives: [
    { attacker: "NOR", defender: "VER", lap_alerted: 22, lap_actual: 25, was_successful: true },
  ],
  false_positives: [],
  false_negatives: [
    { attacker: "LEC", defender: "HAM", lap_alerted: null, lap_actual: 32, was_successful: true },
    { attacker: "SAI", defender: "RUS", lap_alerted: null, lap_actual: 44, was_successful: true },
  ],
};

// ─── Helper ───────────────────────────────────────────────────────────────────

type HookReturn = ReturnType<typeof useBacktest>;

function makeResult(overrides: Partial<HookReturn> = {}): HookReturn {
  return {
    data: undefined,
    isLoading: false,
    isError: false,
    isPending: false,
    isSuccess: false,
    error: null,
    ...overrides,
  } as HookReturn;
}

function mockBoth(scipy: Partial<HookReturn>, xgb: Partial<HookReturn>) {
  mockHook.mockImplementation((_sessionId, predictor) => {
    if (predictor === "scipy") return makeResult(scipy);
    return makeResult(xgb);
  });
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("BacktestView", () => {
  beforeEach(() => {
    mockBoth({}, {});
  });

  it("shows empty state when no session is selected", () => {
    render(<BacktestView />);
    expect(screen.getByTestId("backtest-empty")).toBeInTheDocument();
    expect(
      screen.getByText("Select a session to load backtest results."),
    ).toBeInTheDocument();
  });

  it("shows empty state when sessionId is null", () => {
    render(<BacktestView sessionId={null} />);
    expect(screen.getByTestId("backtest-empty")).toBeInTheDocument();
  });

  it("shows loading state for both predictors while fetching", () => {
    mockBoth({ isLoading: true }, { isLoading: true });
    render(<BacktestView sessionId="monaco_2024_R" />);
    expect(screen.getByTestId("backtest-loading-scipy")).toBeInTheDocument();
    expect(screen.getByTestId("backtest-loading-xgboost")).toBeInTheDocument();
  });

  it("renders scipy and xgboost panels when data is available", () => {
    mockBoth({ data: SCIPY_RESULT }, { data: XGB_RESULT });
    render(<BacktestView sessionId="monaco_2024_R" />);
    expect(screen.getByTestId("backtest-panel-scipy")).toBeInTheDocument();
    expect(screen.getByTestId("backtest-panel-xgboost")).toBeInTheDocument();
  });

  it("renders precision/recall/f1 as percentages", () => {
    mockBoth({ data: SCIPY_RESULT }, { data: XGB_RESULT });
    render(<BacktestView sessionId="monaco_2024_R" />);
    // scipy: 75%, 60%, 67%
    expect(screen.getByText("75%")).toBeInTheDocument();
    expect(screen.getByText("60%")).toBeInTheDocument();
    expect(screen.getByText("67%")).toBeInTheDocument();
    // xgboost: 80%, 65%, 72%
    expect(screen.getByText("80%")).toBeInTheDocument();
    expect(screen.getByText("65%")).toBeInTheDocument();
    expect(screen.getByText("72%")).toBeInTheDocument();
  });

  it("renders TP rows with attacker and defender codes", () => {
    mockBoth({ data: SCIPY_RESULT }, { data: XGB_RESULT });
    render(<BacktestView sessionId="monaco_2024_R" />);
    // NOR appears in both scipy TPs and xgb TPs
    const norCells = screen.getAllByText("NOR");
    expect(norCells.length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("VER").length).toBeGreaterThanOrEqual(1);
  });

  it("renders FP rows in scipy but not in xgboost", () => {
    mockBoth({ data: SCIPY_RESULT }, { data: XGB_RESULT });
    render(<BacktestView sessionId="monaco_2024_R" />);
    // PIA only in scipy FP
    expect(screen.getByText("PIA")).toBeInTheDocument();
  });

  it("renders FN rows", () => {
    mockBoth({ data: SCIPY_RESULT }, { data: XGB_RESULT });
    render(<BacktestView sessionId="monaco_2024_R" />);
    // SAI in scipy FN and xgb FN
    const saiCells = screen.getAllByText("SAI");
    expect(saiCells.length).toBeGreaterThanOrEqual(1);
  });

  it("shows lap numbers formatted as L<n>", () => {
    mockBoth({ data: SCIPY_RESULT }, { data: XGB_RESULT });
    render(<BacktestView sessionId="monaco_2024_R" />);
    expect(screen.getAllByText("L23").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("L25").length).toBeGreaterThanOrEqual(1);
  });

  it("shows — for null lap values", () => {
    mockBoth({ data: SCIPY_RESULT }, { data: XGB_RESULT });
    render(<BacktestView sessionId="monaco_2024_R" />);
    // FP row has lap_actual=null and FN rows have lap_alerted=null
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThan(0);
  });

  it("shows xgboost unavailable state when xgboost errors but scipy works", () => {
    mockBoth({ data: SCIPY_RESULT }, { isError: true });
    render(<BacktestView sessionId="monaco_2024_R" />);
    // scipy results visible
    expect(screen.getByText("75%")).toBeInTheDocument();
    // xgboost shows unavailable
    expect(screen.getByTestId("backtest-unavailable-xgboost")).toBeInTheDocument();
    expect(
      screen.getByText("No curated backtest data for this session yet."),
    ).toBeInTheDocument();
  });

  it("shows scipy unavailable when scipy errors but xgboost works", () => {
    mockBoth({ isError: true }, { data: XGB_RESULT });
    render(<BacktestView sessionId="monaco_2024_R" />);
    expect(screen.getByTestId("backtest-unavailable-scipy")).toBeInTheDocument();
    // xgboost results still visible
    expect(screen.getByText("80%")).toBeInTheDocument();
  });

  it("shows both unavailable when both predictors error", () => {
    mockBoth({ isError: true }, { isError: true });
    render(<BacktestView sessionId="monaco_2024_R" />);
    expect(screen.getByTestId("backtest-unavailable-scipy")).toBeInTheDocument();
    expect(screen.getByTestId("backtest-unavailable-xgboost")).toBeInTheDocument();
  });

  it("shows session id in header when session is selected", () => {
    mockBoth({ data: SCIPY_RESULT }, { data: XGB_RESULT });
    render(<BacktestView sessionId="monaco_2024_R" />);
    expect(screen.getByText("monaco_2024_R")).toBeInTheDocument();
  });

  it("shows TP/FP/FN counts in panel header", () => {
    mockBoth({ data: SCIPY_RESULT }, { data: XGB_RESULT });
    render(<BacktestView sessionId="monaco_2024_R" />);
    // scipy: 2 TP, 1 FP, 1 FN
    expect(screen.getByText("2 TP · 1 FP · 1 FN")).toBeInTheDocument();
    // xgboost: 1 TP, 0 FP, 2 FN
    expect(screen.getByText("1 TP · 0 FP · 2 FN")).toBeInTheDocument();
  });
});
