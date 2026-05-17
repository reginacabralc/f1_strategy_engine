import { useMemo, useState } from "react";
import { TopBar } from "./components/TopBar";
import { Sidebar, type NavId } from "./components/Sidebar";
import { ReplayControls } from "./components/ReplayControls";
import { UndercutBanner } from "./components/UndercutBanner";
import { OverviewPanel } from "./components/panels/OverviewPanel";
import { TimingPanel } from "./components/panels/TimingPanel";
import { StrategyPanel } from "./components/panels/StrategyPanel";
import { TyresPanel } from "./components/panels/TyresPanel";
import { TrackPanel } from "./components/panels/TrackPanel";
import { WeatherPanel } from "./components/panels/WeatherPanel";
import { useSessions } from "./hooks/useSessions";
import { useRaceFeed } from "./hooks/useRaceFeed";

export function App() {
  const [selectedSession, setSelectedSession] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<NavId>("overview");
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
    return (
      sessions.find((s) => s.session_id === selectedSession)?.total_laps ??
      undefined
    );
  }, [selectedSession, sessions]);

  const isLive = status === "open" && replayState?.state === "started";

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
        <Sidebar activeTab={activeTab} onSelectTab={setActiveTab} />

        <main className="flex-1 flex flex-col overflow-hidden min-w-0">
          <UndercutBanner alerts={alerts} />

          {!selectedSession && (
            <div
              className="m-3 flex items-center gap-2 px-3 py-2 rounded-md bg-pitwall-panel border border-pitwall-border"
              data-testid="no-session-hint"
            >
              <span className="text-base leading-none" aria-hidden="true">
                👆
              </span>
              <span className="text-[11px] text-pitwall-muted">
                Select a session from the dropdown above, then tick{" "}
                <span className="font-bold">Demo Mode</span> in the footer and
                press Play to start a 15-minute live race demo.
              </span>
            </div>
          )}

          <div className="flex-1 overflow-y-auto p-3 min-w-0 min-h-0">
            {activeTab === "overview" && (
              <OverviewPanel
                snapshot={snapshot}
                alerts={alerts}
                circuit={circuit}
                totalLaps={totalLaps}
                isLive={isLive}
              />
            )}
            {activeTab === "timing" && (
              <TimingPanel
                snapshot={snapshot}
                connectionStatus={status}
                activePredictor={snapshot?.active_predictor}
              />
            )}
            {activeTab === "strategy" && (
              <StrategyPanel
                snapshot={snapshot}
                alerts={alerts}
                sessionId={selectedSession}
              />
            )}
            {activeTab === "tyres" && (
              <TyresPanel snapshot={snapshot} circuit={circuit} />
            )}
            {activeTab === "track" && (
              <TrackPanel
                snapshot={snapshot}
                circuit={circuit}
                totalLaps={totalLaps}
                isLive={isLive}
              />
            )}
            {activeTab === "weather" && <WeatherPanel snapshot={snapshot} />}
            {activeTab === "settings" && (
              <div className="text-pitwall-muted text-sm">
                Settings (V2). For now, configuration lives in{" "}
                <code className="font-mono text-xs">.env</code> and{" "}
                <code className="font-mono text-xs">docker-compose.yaml</code>.
              </div>
            )}
          </div>
        </main>
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
