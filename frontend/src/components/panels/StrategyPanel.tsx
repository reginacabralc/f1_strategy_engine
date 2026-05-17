import type { AlertPayload } from "../../api/ws";
import type { RaceSnapshot } from "../../api/types";
import { AlertPanel } from "../AlertPanel";
import { BacktestView } from "../BacktestView";
import { PredictorToggle } from "../PredictorToggle";

interface Props {
  snapshot: RaceSnapshot | null;
  alerts: AlertPayload[];
  sessionId: string | null;
}

export function StrategyPanel({ snapshot, alerts, sessionId }: Props) {
  const drivers = snapshot?.drivers ?? [];
  const scoreboard = drivers
    .filter((d) => d.undercut_score != null && d.undercut_score! > 0)
    .sort(
      (a, b) => (b.undercut_score ?? 0) - (a.undercut_score ?? 0),
    )
    .slice(0, 6);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 h-full min-h-0">
      <div className="lg:col-span-2 flex flex-col gap-3 min-h-0">
        <section
          aria-label="Live undercut scoreboard"
          className="panel flex flex-col"
        >
          <div className="px-3 py-2 border-b border-pitwall-border">
            <span className="label-caps">Live Undercut Scoreboard</span>
          </div>
          {scoreboard.length === 0 ? (
            <p className="px-3 py-6 text-xs text-pitwall-muted text-center">
              No active undercut signals. Start a demo replay to see live model output.
            </p>
          ) : (
            <ul className="divide-y divide-pitwall-border">
              {scoreboard.map((d) => {
                const score = d.undercut_score ?? 0;
                const pct = Math.round(score * 100);
                const tone =
                  score >= 0.65
                    ? "text-pitwall-accent"
                    : score >= 0.35
                      ? "text-pitwall-yellow"
                      : "text-pitwall-green";
                return (
                  <li
                    key={d.driver_code}
                    className="flex items-center gap-3 px-3 py-2"
                  >
                    <span className="font-mono text-xs text-pitwall-muted w-6">
                      P{d.position}
                    </span>
                    <span className="font-mono font-bold text-white w-12">
                      {d.driver_code}
                    </span>
                    <div className="flex-1 h-2 bg-pitwall-border/40 rounded">
                      <div
                        className={`h-full rounded ${tone.replace("text-", "bg-")}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className={`font-mono text-xs ${tone} w-10 text-right`}>
                      {pct}%
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
        <BacktestView sessionId={sessionId} />
      </div>
      <div className="flex flex-col gap-3 min-h-0">
        <AlertPanel alerts={alerts} />
        <PredictorToggle activePredictor={snapshot?.active_predictor} />
      </div>
    </div>
  );
}
