import { useState } from "react";
import { SessionPicker } from "./components/SessionPicker";
import { RaceTable } from "./components/RaceTable";

export function App() {
  const [selectedSession, setSelectedSession] = useState<string | null>(null);

  return (
    <div className="min-h-screen bg-pitwall-bg text-pitwall-text">
      <header className="border-b border-pitwall-border bg-pitwall-surface px-6 py-4 flex items-center gap-4">
        <span className="text-pitwall-accent font-bold text-lg tracking-tight">
          PitWall
        </span>
        <span className="text-pitwall-muted text-sm hidden sm:block">
          F1 Strategy Engine
        </span>
        <div className="ml-auto">
          <SessionPicker
            selected={selectedSession}
            onSelect={setSelectedSession}
          />
        </div>
      </header>

      <main className="px-6 py-6 max-w-7xl mx-auto space-y-6">
        <section>
          <h2 className="text-xs font-semibold uppercase tracking-widest text-pitwall-muted mb-3">
            Race Order
            {selectedSession && (
              <span className="ml-2 text-pitwall-text font-normal normal-case tracking-normal">
                — {selectedSession}
              </span>
            )}
          </h2>
          <RaceTable />
        </section>

        <section className="rounded-lg border border-pitwall-border bg-pitwall-surface px-6 py-5">
          <p className="text-pitwall-muted text-sm">
            <span className="text-yellow-400 font-semibold">Coming soon:</span>{" "}
            Live WebSocket feed, degradation chart, alert panel, and predictor
            toggle (Stream C Day 4–6).
          </p>
        </section>
      </main>
    </div>
  );
}
