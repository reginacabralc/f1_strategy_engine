import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../api/client");

import { startReplay, stopReplay } from "../api/client";
import { ReplayControls } from "./ReplayControls";

const mockStartReplay = vi.mocked(startReplay);
const mockStopReplay = vi.mocked(stopReplay);

describe("ReplayControls", () => {
  beforeEach(() => {
    mockStartReplay.mockReset();
    mockStopReplay.mockReset();
    mockStartReplay.mockResolvedValue({
      run_id: "run-1",
      session_id: "monaco_2024_R",
      speed_factor: 30,
      started_at: "2024-05-26T13:00:00Z",
      pace_predictor: "scipy",
    });
    mockStopReplay.mockResolvedValue({ stopped: true, run_id: "run-1" });
  });

  it("keeps play disabled until a session is selected", () => {
    render(<ReplayControls selectedSession={null} />);

    expect(screen.getByLabelText("Start replay")).toBeDisabled();
    expect(screen.getByText("Select a session to enable replay")).toBeInTheDocument();
  });

  it("starts replay for the selected session at the selected speed", async () => {
    render(<ReplayControls selectedSession="monaco_2024_R" />);

    fireEvent.click(screen.getByLabelText("Set speed x100"));
    fireEvent.click(screen.getByLabelText("Start replay"));

    await waitFor(() => {
      expect(mockStartReplay).toHaveBeenCalledWith("monaco_2024_R", 100, false);
    });
  });

  it("stops replay when replay state is started", async () => {
    render(<ReplayControls selectedSession="monaco_2024_R" replayState="started" />);

    fireEvent.click(screen.getByLabelText("Stop replay"));

    await waitFor(() => {
      expect(mockStopReplay).toHaveBeenCalledOnce();
    });
  });

  it("renders the live lap counter", () => {
    render(<ReplayControls selectedSession="monaco_2024_R" currentLap={18} totalLaps={78} />);

    expect(screen.getByTestId("replay-current-lap")).toHaveTextContent("18");
    expect(screen.getByTestId("replay-total-laps")).toHaveTextContent("78");
  });

  it("enables play when a session is selected", () => {
    render(<ReplayControls selectedSession="monaco_2024_R" />);

    expect(screen.getByLabelText("Start replay")).not.toBeDisabled();
  });

  it("marks skip and step buttons as not supported in V1", () => {
    render(<ReplayControls selectedSession="monaco_2024_R" />);

    for (const label of ["Skip to start", "Step back", "Step forward", "Skip to end"]) {
      const btn = screen.getByLabelText(label);
      expect(btn).toBeDisabled();
      expect(btn).toHaveAttribute("title", "Not supported in V1");
    }
  });

  it("shows Stop button and running status when replayState is started", () => {
    render(<ReplayControls selectedSession="monaco_2024_R" replayState="started" />);

    expect(screen.getByLabelText("Stop replay")).toBeInTheDocument();
    expect(screen.getByText("Replay running")).toBeInTheDocument();
  });

  it("shows error message when startReplay fails", async () => {
    mockStartReplay.mockRejectedValueOnce(new Error("API 503: Service Unavailable"));
    render(<ReplayControls selectedSession="monaco_2024_R" />);

    fireEvent.click(screen.getByLabelText("Start replay"));

    await waitFor(() => {
      expect(screen.getByTestId("replay-error")).toHaveTextContent("API 503: Service Unavailable");
    });
  });

  it("shows error message when stopReplay fails", async () => {
    mockStopReplay.mockRejectedValueOnce(new Error("Network error"));
    render(<ReplayControls selectedSession="monaco_2024_R" replayState="started" />);

    fireEvent.click(screen.getByLabelText("Stop replay"));

    await waitFor(() => {
      expect(screen.getByTestId("replay-error")).toHaveTextContent("Network error");
    });
  });

  it("sends demo_mode=true to startReplay when toggle is checked and auto-switches to 6× speed", async () => {
    render(<ReplayControls selectedSession="monaco_2024_R" />);

    // Checking Demo Mode auto-switches the speed to 6× (15-min class-demo target).
    fireEvent.click(screen.getByTestId("demo-mode-toggle"));
    fireEvent.click(screen.getByLabelText("Start replay"));

    await waitFor(() => {
      expect(mockStartReplay).toHaveBeenCalledWith("monaco_2024_R", 6, true);
    });
  });

  it("sends demo_mode=false to startReplay when toggle is unchecked (default)", async () => {
    render(<ReplayControls selectedSession="monaco_2024_R" />);

    fireEvent.click(screen.getByLabelText("Start replay"));

    await waitFor(() => {
      expect(mockStartReplay).toHaveBeenCalledWith("monaco_2024_R", 30, false);
    });
  });

  it("demo toggle is disabled when no session is selected", () => {
    render(<ReplayControls selectedSession={null} />);

    expect(screen.getByTestId("demo-mode-toggle")).toBeDisabled();
  });
});
