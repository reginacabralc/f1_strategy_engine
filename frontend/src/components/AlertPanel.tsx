// Placeholder alert panel — will be populated by the WebSocket alert stream in Day 5.

type AlertLevel = "critical" | "warning" | "info";

interface AlertItem {
  id: string;
  level: AlertLevel;
  driver: string;
  message: string;
  lap: number;
}

const MOCK_ALERTS: AlertItem[] = [
  {
    id: "a1",
    level: "critical",
    driver: "LEC",
    message: "Undercut window open — pit now",
    lap: 27,
  },
  {
    id: "a2",
    level: "warning",
    driver: "SAI",
    message: "Gap closing — monitor",
    lap: 27,
  },
  {
    id: "a3",
    level: "info",
    driver: "HAM",
    message: "Pit window opens in 3 laps",
    lap: 27,
  },
];

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

export function AlertPanel() {
  return (
    <section
      aria-label="Strategy alerts"
      className="panel flex flex-col overflow-hidden"
    >
      <div className="flex items-center justify-between px-3 py-2 border-b border-pitwall-border shrink-0">
        <span className="label-caps">Strategy Alerts</span>
        <span className="text-[10px] font-mono text-pitwall-muted">
          {MOCK_ALERTS.length} active
        </span>
      </div>

      <ul className="flex flex-col gap-2 p-2 overflow-y-auto">
        {MOCK_ALERTS.map((alert) => {
          const s = LEVEL_STYLES[alert.level];
          return (
            <li
              key={alert.id}
              className="relative flex gap-2.5 bg-pitwall-panel rounded-md px-3 py-2.5 overflow-hidden"
            >
              {/* left accent bar */}
              <span
                className={`absolute left-0 top-0 bottom-0 w-0.5 rounded-r ${s.bar}`}
              />

              <div className="flex flex-col gap-0.5 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-bold text-pitwall-text">
                    {alert.driver}
                  </span>
                  <span
                    className={`inline-flex px-1 py-px rounded text-[9px] font-bold border ${s.badge}`}
                  >
                    {LEVEL_LABEL[alert.level]}
                  </span>
                  <span className="ml-auto text-[10px] font-mono text-pitwall-muted">
                    L{alert.lap}
                  </span>
                </div>
                <p className="text-xs text-pitwall-muted leading-snug">
                  {alert.message}
                </p>
              </div>
            </li>
          );
        })}
      </ul>

      <p className="px-3 py-2 text-[10px] text-pitwall-muted border-t border-pitwall-border text-center shrink-0">
        Live alerts connect in Day 5
      </p>
    </section>
  );
}
