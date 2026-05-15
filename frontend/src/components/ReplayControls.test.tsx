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
      expect(mockStartReplay).toHaveBeenCalledWith("monaco_2024_R", 100);
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
});
