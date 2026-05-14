interface Props {
  label: string;
  value: string;
  unit?: string;
  trend?: "up" | "down" | "neutral";
  alert?: "green" | "yellow" | "red";
}

const ALERT_CLASSES: Record<NonNullable<Props["alert"]>, string> = {
  green: "border-pitwall-green/30 text-pitwall-green",
  yellow: "border-pitwall-yellow/30 text-pitwall-yellow",
  red: "border-pitwall-accent/30 text-pitwall-accent",
};

const TREND_SYMBOL: Record<NonNullable<Props["trend"]>, string> = {
  up: "↑",
  down: "↓",
  neutral: "→",
};

export function MetricCard({ label, value, unit, trend, alert }: Props) {
  const alertClass = alert ? ALERT_CLASSES[alert] : "border-pitwall-border";

  return (
    <div
      className={`bg-pitwall-surface rounded-lg border px-3 py-2.5 flex flex-col gap-1 ${alertClass}`}
    >
      <span className="label-caps">{label}</span>
      <div className="flex items-baseline gap-1.5">
        <span
          className={`text-xl font-mono font-bold leading-none ${alert ? ALERT_CLASSES[alert].split(" ")[1] : "text-pitwall-text"}`}
        >
          {value}
        </span>
        {unit && (
          <span className="text-xs text-pitwall-muted font-mono">{unit}</span>
        )}
        {trend && (
          <span
            className={`text-xs ml-auto ${trend === "up" ? "text-pitwall-orange" : trend === "down" ? "text-pitwall-green" : "text-pitwall-muted"}`}
            aria-label={`Trend: ${trend}`}
          >
            {TREND_SYMBOL[trend]}
          </span>
        )}
      </div>
    </div>
  );
}
