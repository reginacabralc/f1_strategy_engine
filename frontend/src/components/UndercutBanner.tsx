import { useEffect, useState } from "react";
import type { AlertPayload } from "../api/ws";

interface Props {
  alerts: AlertPayload[];
}

// The banner displays the most recent UNDERCUT_VIABLE alert in a big,
// impossible-to-miss strip across the top of the dashboard's main content.
// It auto-dismisses after AUTO_DISMISS_MS or when the user clicks "×".
//
// Multiple predictors may fire alerts for the same (attacker, defender, lap)
// pair within milliseconds of each other; we group those into a single banner
// row that shows badges for every predictor that agreed.
const AUTO_DISMISS_MS = 12_000;

function predictorBadgeStyles(predictor: string): string {
  if (predictor === "scipy")
    return "bg-blue-400/20 text-blue-200 border-blue-400/50";
  if (predictor === "xgboost")
    return "bg-purple-400/20 text-purple-200 border-purple-400/50";
  if (predictor === "causal")
    return "bg-pitwall-green/20 text-pitwall-green border-pitwall-green/50";
  return "bg-pitwall-muted/20 text-pitwall-muted border-pitwall-muted/50";
}

interface GroupedAlert {
  key: string;
  lap_number: number;
  attacker_code: string;
  defender_code: string;
  predictors: Set<string>;
  representative: AlertPayload;
}

function groupAlerts(alerts: AlertPayload[]): GroupedAlert[] {
  const map = new Map<string, GroupedAlert>();
  for (const a of alerts) {
    if (a.alert_type !== "UNDERCUT_VIABLE") continue;
    const key = `${a.session_id}:${a.lap_number}:${a.attacker_code}:${a.defender_code}`;
    const existing = map.get(key);
    if (existing) {
      existing.predictors.add(a.predictor_used);
    } else {
      map.set(key, {
        key,
        lap_number: a.lap_number,
        attacker_code: a.attacker_code,
        defender_code: a.defender_code,
        predictors: new Set([a.predictor_used]),
        representative: a,
      });
    }
  }
  // Newest first (alerts arrive newest-first from the useRaceFeed buffer)
  return [...map.values()];
}

export function UndercutBanner({ alerts }: Props) {
  const grouped = groupAlerts(alerts);
  const latest = grouped[0]; // alerts is already newest-first
  const [dismissedKey, setDismissedKey] = useState<string | null>(null);

  // Reset dismissal when a new alert key arrives.
  useEffect(() => {
    if (latest && latest.key !== dismissedKey) {
      // Auto-dismiss timer
      const t = setTimeout(() => setDismissedKey(latest.key), AUTO_DISMISS_MS);
      return () => clearTimeout(t);
    }
  }, [latest?.key, dismissedKey, latest]);

  if (!latest || latest.key === dismissedKey) return null;

  const a = latest.representative;
  const confidencePct =
    a.confidence != null ? Math.round(a.confidence * 100) : null;
  const gainSec =
    a.estimated_gain_ms != null
      ? (a.estimated_gain_ms / 1000).toFixed(1)
      : null;

  return (
    <div
      role="alert"
      aria-live="assertive"
      data-testid="undercut-banner"
      className="relative w-full bg-gradient-to-r from-pitwall-accent/30 via-pitwall-accent/15 to-pitwall-accent/30 border-y-2 border-pitwall-accent shadow-[0_0_24px_rgba(220,38,38,0.35)] animate-[pulse_1.6s_ease-in-out_3]"
    >
      <div className="flex items-center gap-4 px-4 py-3">
        <div className="flex flex-col items-center justify-center px-3 py-1 bg-pitwall-accent text-white rounded font-mono font-extrabold tracking-widest text-xs shrink-0 shadow-md">
          <span>UNDERCUT</span>
          <span>VIABLE</span>
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-3 flex-wrap">
            <span className="font-mono font-bold text-2xl text-white">
              {latest.attacker_code}
              <span className="text-pitwall-accent mx-2">→</span>
              {latest.defender_code}
            </span>
            <span className="text-pitwall-muted text-xs uppercase tracking-wide">
              Lap{" "}
              <span className="text-white font-mono font-bold text-sm">
                {latest.lap_number}
              </span>
            </span>
            {confidencePct !== null && (
              <span className="text-pitwall-muted text-xs uppercase tracking-wide">
                Confidence{" "}
                <span className="text-white font-mono font-bold text-sm">
                  {confidencePct}%
                </span>
              </span>
            )}
            {gainSec && Number(gainSec) > 0 && (
              <span className="text-pitwall-muted text-xs uppercase tracking-wide">
                Est. gain{" "}
                <span className="text-white font-mono font-bold text-sm">
                  {gainSec}s
                </span>
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 mt-1.5">
            <span className="text-[10px] text-pitwall-muted uppercase tracking-wider">
              Models agreed:
            </span>
            {[...latest.predictors].map((p) => (
              <span
                key={p}
                className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded border font-bold ${predictorBadgeStyles(p)}`}
              >
                {p}
              </span>
            ))}
            {a.demo_source && (
              <span
                className="text-[10px] font-mono uppercase px-2 py-0.5 rounded border border-pitwall-muted/40 text-pitwall-muted"
                title="Curated from observed pit-cycle exchanges"
              >
                {a.demo_source}
              </span>
            )}
          </div>
        </div>

        <button
          onClick={() => setDismissedKey(latest.key)}
          aria-label="Dismiss undercut alert"
          className="shrink-0 w-7 h-7 flex items-center justify-center rounded text-pitwall-muted hover:text-white hover:bg-white/10 transition-colors text-lg leading-none"
        >
          ×
        </button>
      </div>
    </div>
  );
}
