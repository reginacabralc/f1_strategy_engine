import { useMemo, useState } from "react";
import { TopBar } from "./components/TopBar";
import { Sidebar } from "./components/Sidebar";
import { RaceTable } from "./components/RaceTable";
import { AlertPanel } from "./components/AlertPanel";
import { MetricCard } from "./components/MetricCard";
import { DegradationChart } from "./components/DegradationChart";
import { TrackMapPanel } from "./components/TrackMapPanel";
import { ReplayControls } from "./components/ReplayControls";
import { PredictorToggle } from "./components/PredictorToggle";
import { BacktestView } from "./components/BacktestView";
import { useSessions } from "./hooks/useSessions";
import { useRaceFeed } from "./hooks/useRaceFeed";

const METRICS = [
  { label: "Track Temp", value: "42", unit: "°C", trend: "up" as const },
  { label: "Air Temp", value: "28", unit: "°C", trend: "neutral" as const },
  { label: "Pit Loss", value: "~23", unit: "s", trend: "neutral" as const },
  {
    label: "Undercut Risk",
    value: "HIGH",
    alert: "red" as const,
  },
];

export function App() {
  const [selectedSession, setSelectedSession] = useState<string | null>(null);
  const { data: sessions } = useSessions();
  const { status, snapshot, alerts, replayState } = useRaceFeed();
  const circuit = useMemo(() => {
    if (!selectedSession || !sessions) return "monaco";
    return (
      sessions.find((s) => s.session_id === selectedSession)?.circuit_id ??
      "monaco"
    );
  }, [selectedSession, sessions]);
  const totalLaps = useMemo(() => {
    if (!selectedSession || !sessions) return undefined;
    return sessions.find((s) => s.session_id === selectedSession)?.total_laps ?? undefined;
  }, [selectedSession, sessions]);

  return (
    <div className="h-full flex flex-col bg-pitwall-bg overflow-hidden">
      <TopBar
        selectedSession={selectedSession}
        onSelectSession={setSelectedSession}
        connectionStatus={status}
        activePredictor={snapshot?.active_predictor}
        currentLap={snapshot?.current_lap}
        totalLaps={totalLaps}
      />

      <div className="flex flex-1 overflow-hidden">
        <Sidebar />

        {/* Main content + right column */}
        <div className="flex flex-1 overflow-hidden gap-0">
          {/* Centre: table + degradation */}
          <main className="flex-1 flex flex-col gap-3 p-3 overflow-y-auto min-w-0">
            {/* No-session hint */}
            {!selectedSession && (
              <div
                className="flex items-center gap-2 px-3 py-2 rounded-md bg-pitwall-panel border border-pitwall-border"
                data-testid="no-session-hint"
              >
                <span className="text-base leading-none" aria-hidden="true">👆</span>
                <span className="text-[11px] text-pitwall-muted">
                  Select a session from the dropdown above, then use Replay Controls to start playback.
                </span>
              </div>
            )}

            {/* Section label */}
            <div className="flex items-center gap-2">
              <span className="label-caps">Race Order</span>
              {selectedSession && (
                <span className="text-[10px] font-mono text-pitwall-muted">
                  {selectedSession}
                </span>
              )}
            </div>

            <RaceTable
              drivers={snapshot?.drivers}
              isLive={status === "open"}
              connectionStatus={status}
              activePredictor={snapshot?.active_predictor}
            />

            {/* Lower panels: Degradation + Track Map, side-by-side on wider screens */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <DegradationChart circuit={circuit} />
              <TrackMapPanel />
            </div>

            <BacktestView sessionId={selectedSession} />
          </main>

          {/* Right column: alerts + predictor toggle + metrics */}
          <aside className="w-64 shrink-0 flex flex-col gap-3 p-3 border-l border-pitwall-border overflow-y-auto">
            <AlertPanel alerts={alerts} />

            <PredictorToggle activePredictor={snapshot?.active_predictor} />

            <div>
              <span className="label-caps block mb-2">Track Conditions</span>
              <div className="grid grid-cols-2 gap-2">
                {METRICS.map((m) => (
                  <MetricCard key={m.label} {...m} />
                ))}
              </div>
            </div>
          </aside>
        </div>
      </div>

      <ReplayControls
        selectedSession={selectedSession}
        replayState={replayState?.state}
        currentLap={snapshot?.current_lap}
        totalLaps={totalLaps}
      />
    </div>
  );
}
