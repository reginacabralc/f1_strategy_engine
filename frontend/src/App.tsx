import { useMemo, useState } from "react";
import { TopBar } from "./components/TopBar";
import { Sidebar } from "./components/Sidebar";
import { RaceTable } from "./components/RaceTable";
import { AlertPanel } from "./components/AlertPanel";
import { MetricCard } from "./components/MetricCard";
import { DegradationChart } from "./components/DegradationChart";
import { TrackMapPanel } from "./components/TrackMapPanel";
import { ReplayControls } from "./components/ReplayControls";
import { useSessions } from "./hooks/useSessions";

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
  const circuit = useMemo(() => {
    if (!selectedSession || !sessions) return "monaco";
    return (
      sessions.find((s) => s.session_id === selectedSession)?.circuit_id ??
      "monaco"
    );
  }, [selectedSession, sessions]);

  return (
    <div className="h-full flex flex-col bg-pitwall-bg overflow-hidden">
      <TopBar
        selectedSession={selectedSession}
        onSelectSession={setSelectedSession}
      />

      <div className="flex flex-1 overflow-hidden">
        <Sidebar />

        {/* Main content + right column */}
        <div className="flex flex-1 overflow-hidden gap-0">
          {/* Centre: table + degradation */}
          <main className="flex-1 flex flex-col gap-3 p-3 overflow-y-auto min-w-0">
            {/* Section label */}
            <div className="flex items-center gap-2">
              <span className="label-caps">Race Order</span>
              {selectedSession && (
                <span className="text-[10px] font-mono text-pitwall-muted">
                  {selectedSession}
                </span>
              )}
            </div>

            <RaceTable />

            {/* Lower panels: Degradation + Track Map, side-by-side on wider screens */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <DegradationChart circuit={circuit} />
              <TrackMapPanel />
            </div>
          </main>

          {/* Right column: alerts + metrics */}
          <aside className="w-64 shrink-0 flex flex-col gap-3 p-3 border-l border-pitwall-border overflow-y-auto">
            <AlertPanel />

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

      <ReplayControls />
    </div>
  );
}
