import { useState } from "react";
import { startReplay, stopReplay } from "../api/client";

// 6× plays a 90-minute race in ~15 minutes wall-clock — the class-demo default.
// Other speeds remain available for quick tests / dev replays.
const SPEEDS = [1, 6, 10, 30, 100, 1000] as const;

type ReplayState = "started" | "stopped" | "finished" | null | undefined;

interface ReplayControlsProps {
  selectedSession: string | null;
  replayState?: ReplayState;
  currentLap?: number;
  totalLaps?: number;
}

function SkipBackIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
      <polygon points="7,2 1,7 7,12" />
      <polygon points="13,2 7,7 13,12" />
    </svg>
  );
}

function StepBackIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
      <polygon points="10,2 4,7 10,12" />
      <rect x="2" y="2" width="2" height="10" />
    </svg>
  );
}

function PlayIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
      <polygon points="3,1 13,7 3,13" />
    </svg>
  );
}

function StopIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
      <rect x="3" y="3" width="8" height="8" />
    </svg>
  );
}

function StepForwardIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
      <polygon points="4,2 10,7 4,12" />
      <rect x="10" y="2" width="2" height="10" />
    </svg>
  );
}

function SkipForwardIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
      <polygon points="1,2 7,7 1,12" />
      <polygon points="7,2 13,7 7,12" />
    </svg>
  );
}

const SIDE_BUTTONS = [
  { icon: <SkipBackIcon />, label: "Skip to start" },
  { icon: <StepBackIcon />, label: "Step back" },
  { icon: <StepForwardIcon />, label: "Step forward" },
  { icon: <SkipForwardIcon />, label: "Skip to end" },
];

export function ReplayControls({
  selectedSession,
  replayState,
  currentLap,
  totalLaps,
}: ReplayControlsProps) {
  const [speed, setSpeed] = useState<(typeof SPEEDS)[number]>(30);
  const [demoMode, setDemoMode] = useState(false);
  // When Demo Mode is toggled on, switch to 6× so the race lasts ~15 min
  // wall-clock (the class-demo target). Reset to 30× if Demo Mode is turned off.
  function toggleDemoMode(active: boolean): void {
    setDemoMode(active);
    setSpeed(active ? 6 : 30);
  }
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isStarted = replayState === "started";
  const safeCurrentLap = currentLap ?? 0;
  const safeTotalLaps = totalLaps ?? 0;
  const timelinePercent =
    safeTotalLaps > 0
      ? Math.min(100, Math.max(0, (safeCurrentLap / safeTotalLaps) * 100))
      : 0;

  async function handleStart() {
    if (!selectedSession) return;
    setIsPending(true);
    setError(null);
    try {
      await startReplay(selectedSession, speed, demoMode);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start replay");
    } finally {
      setIsPending(false);
    }
  }

  async function handleStop() {
    setIsPending(true);
    setError(null);
    try {
      await stopReplay();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to stop replay");
    } finally {
      setIsPending(false);
    }
  }

  const statusText = !selectedSession
    ? "Select a session to enable replay"
    : isPending
      ? "Updating replay..."
      : isStarted
        ? "Replay running"
        : "Ready to start replay";

  return (
    <footer
      aria-label="Replay controls"
      className="h-12 shrink-0 bg-pitwall-surface border-t border-pitwall-border flex items-center gap-4 px-4"
    >
      {/* Transport buttons */}
      <div className="flex items-center gap-1">
        {SIDE_BUTTONS.slice(0, 2).map((btn) => (
          <button
            key={btn.label}
            aria-label={btn.label}
            title="Not supported in V1"
            disabled
            className="w-8 h-8 rounded flex items-center justify-center text-pitwall-muted hover:text-pitwall-text hover:bg-pitwall-panel transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {btn.icon}
          </button>
        ))}
        <button
          type="button"
          aria-label={isStarted ? "Stop replay" : "Start replay"}
          disabled={isPending || (!isStarted && !selectedSession)}
          onClick={isStarted ? handleStop : handleStart}
          className="w-8 h-8 rounded flex items-center justify-center text-pitwall-text bg-pitwall-accent/15 hover:bg-pitwall-accent/25 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {isStarted ? <StopIcon /> : <PlayIcon />}
        </button>
        {SIDE_BUTTONS.slice(2).map((btn) => (
          <button
            key={btn.label}
            aria-label={btn.label}
            title="Not supported in V1"
            disabled
            className="w-8 h-8 rounded flex items-center justify-center text-pitwall-muted hover:text-pitwall-text hover:bg-pitwall-panel transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {btn.icon}
          </button>
        ))}
      </div>

      <div className="w-px h-6 bg-pitwall-border" />

      {/* Speed selector */}
      <div className="flex items-center gap-1">
        <span className="label-caps mr-1">Speed</span>
        {SPEEDS.map((s) => (
          <button
            key={s}
            type="button"
            disabled={isPending}
            onClick={() => setSpeed(s)}
            aria-label={`Set speed x${s}`}
            className={[
              "h-6 px-2 rounded text-[10px] font-mono font-bold border transition-colors",
              s === speed
                ? "bg-pitwall-accent/10 border-pitwall-accent/40 text-pitwall-accent"
                : "border-pitwall-border text-pitwall-muted hover:text-pitwall-text hover:bg-pitwall-panel",
            ].join(" ")}
          >
            ×{s}
          </button>
        ))}
      </div>

      <div className="w-px h-6 bg-pitwall-border" />

      {/* Demo mode toggle */}
      <label
        className="flex items-center gap-1 text-[10px] text-pitwall-muted cursor-pointer select-none"
        title="Class demo mode: relaxed thresholds + scripted alerts + causal observer"
      >
        <input
          type="checkbox"
          checked={demoMode}
          onChange={(e) => toggleDemoMode(e.target.checked)}
          disabled={isPending || !selectedSession}
          className="w-3 h-3 accent-pitwall-accent"
          data-testid="demo-mode-toggle"
        />
        Demo
      </label>

      <div className="w-px h-6 bg-pitwall-border" />

      {/* Lap counter */}
      <div className="flex items-center gap-1.5 text-xs font-mono">
        <span className="text-pitwall-muted">LAP</span>
        <span className="text-pitwall-text font-bold" data-testid="replay-current-lap">
          {currentLap ?? "-"}
        </span>
        <span className="text-pitwall-muted">/</span>
        <span className="text-pitwall-muted" data-testid="replay-total-laps">
          {totalLaps ?? "-"}
        </span>
      </div>

      {/* Timeline track */}
      <div className="flex-1 flex items-center gap-2">
        <div
          className="flex-1 h-1 bg-pitwall-border rounded-full relative cursor-not-allowed"
          aria-label="Replay timeline"
        >
          <div
            className="absolute left-0 top-0 bottom-0 bg-pitwall-accent/60 rounded-full"
            style={{ width: `${timelinePercent}%` }}
          />
          <div
            className="absolute top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full bg-pitwall-accent border-2 border-pitwall-surface shadow -translate-x-1/2"
            style={{ left: `${timelinePercent}%` }}
          />
        </div>
      </div>

      {error ? (
        <span className="text-[10px] text-red-400 ml-1" data-testid="replay-error">
          {error}
        </span>
      ) : (
        <span className="text-[10px] text-pitwall-muted ml-1 hidden sm:inline">
          {statusText}
        </span>
      )}
    </footer>
  );
}
