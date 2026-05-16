import type { AlertPayload } from "../api/ws";
import type { AlertType } from "../api/types";

interface Props {
  alerts?: AlertPayload[];
}

type AlertLevel = "critical" | "warning" | "info";

function alertLevel(type: AlertType): AlertLevel {
  if (type === "UNDERCUT_VIABLE") return "critical";
  if (type === "UNDERCUT_RISK") return "warning";
  return "info";
}

const LEVEL_STYLES: Record<AlertLevel, { bar: string; badge: string; text: string }> = {
  critical: {
    bar: "bg-pitwall-accent",
    badge: "bg-pitwall-accent/10 text-pitwall-accent border-pitwall-accent/40",
    text: "text-pitwall-accent",
  },
  warning: {
    bar: "bg-pitwall-yellow",
    badge: "bg-pitwall-yellow/10 text-pitwall-yellow border-pitwall-yellow/40",
    text: "text-pitwall-yellow",
  },
  info: {
    bar: "bg-pitwall-green",
    badge: "bg-pitwall-green/10 text-pitwall-green border-pitwall-green/40",
    text: "text-pitwall-green",
  },
};

const LEVEL_LABEL: Record<AlertLevel, string> = {
  critical: "CRITICAL",
  warning: "WARN",
  info: "INFO",
};

function msToSec(ms: number): string {
  return `+${(ms / 1000).toFixed(1)}s`;
}

function predictorBadgeColor(predictor?: string): string {
  if (predictor === "scipy") return "text-blue-400 bg-blue-400/10 border-blue-400/40";
  if (predictor === "xgboost") return "text-purple-400 bg-purple-400/10 border-purple-400/40";
  if (predictor === "causal") return "text-pitwall-green bg-pitwall-green/10 border-pitwall-green/40";
  return "text-pitwall-muted bg-pitwall-muted/10 border-pitwall-muted/40";
}

export function AlertPanel({ alerts = [] }: Props) {
  return (
    <section
      aria-label="Strategy alerts"
      className="panel flex flex-col overflow-hidden"
    >
      <div className="flex items-center justify-between px-3 py-2 border-b border-pitwall-border shrink-0">
        <span className="label-caps">Strategy Alerts</span>
        <span className="text-[10px] font-mono text-pitwall-muted">
          {alerts.length} active
        </span>
      </div>

      {alerts.length === 0 ? (
        <p
          className="px-3 py-6 text-[11px] text-pitwall-muted text-center"
          data-testid="alert-empty"
        >
          No alerts — start a replay to receive live strategy alerts
        </p>
      ) : (
        <ul className="flex flex-col gap-2 p-2 overflow-y-auto">
          {alerts.map((alert, idx) => {
            const level = alertLevel(alert.alert_type);
            const s = LEVEL_STYLES[level];
            const isNewest = idx === 0;
            return (
              <li
                key={alert.alert_id}
                className={[
                  "relative flex gap-2.5 bg-pitwall-panel rounded-md px-3 py-2.5 overflow-hidden",
                  isNewest ? "alert-flash" : "",
                ].join(" ")}
              >
                <span
                  className={`absolute left-0 top-0 bottom-0 w-0.5 rounded-r ${s.bar}`}
                />

                <div className="flex flex-col gap-0.5 min-w-0 w-full">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-bold text-pitwall-text">
                      {alert.attacker_code}
                    </span>
                    <span className="text-[9px] text-pitwall-muted">→</span>
                    <span className="text-xs font-semibold text-pitwall-muted">
                      {alert.defender_code}
                    </span>
                    <span
                      className={`inline-flex px-1 py-px rounded text-[9px] font-bold border ${s.badge}`}
                    >
                      {LEVEL_LABEL[level]}
                    </span>
                    {alert.predictor_used && (
                      <span
                        className={`text-[9px] font-mono uppercase px-1.5 py-0.5 rounded border ${predictorBadgeColor(alert.predictor_used)}`}
                        data-testid={`predictor-badge-${alert.predictor_used}`}
                        title={alert.causal_explanations?.[0] ?? alert.demo_source ?? ""}
                      >
                        {alert.predictor_used}
                      </span>
                    )}
                    <span className="ml-auto text-[10px] font-mono text-pitwall-muted">
                      L{alert.lap_number}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className={`text-[10px] font-mono font-semibold ${s.text}`}>
                      {msToSec(alert.estimated_gain_ms)}
                    </span>
                    <span className="text-[10px] text-pitwall-muted">
                      score {Math.round(alert.score * 100)}%
                    </span>
                    <span className="text-[10px] text-pitwall-muted">
                      conf {Math.round(alert.confidence * 100)}%
                    </span>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
