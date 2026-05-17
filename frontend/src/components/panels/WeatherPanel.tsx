import type { RaceSnapshot } from "../../api/types";
import { MetricCard } from "../MetricCard";

interface Props {
  snapshot: RaceSnapshot | null;
}

function rainBucket(snapshot: RaceSnapshot | null): {
  value: string;
  alert?: "red" | "yellow" | "green";
} {
  // V1 snapshots do not include rainfall directly — we infer from track_status.
  const status = snapshot?.track_status ?? "GREEN";
  if (status === "RED") return { value: "RACE STOPPED", alert: "red" };
  if (status === "YELLOW" || status === "VSC" || status === "SC")
    return { value: "CAUTION", alert: "yellow" };
  return { value: "DRY / GREEN", alert: "green" };
}

export function WeatherPanel({ snapshot }: Props) {
  const trackTemp =
    snapshot?.track_temp_c != null ? snapshot.track_temp_c.toFixed(1) : "—";
  const airTemp =
    snapshot?.air_temp_c != null ? snapshot.air_temp_c.toFixed(1) : "—";
  const humidity =
    snapshot?.humidity_pct != null
      ? Math.round(snapshot.humidity_pct).toString()
      : "—";

  const delta =
    snapshot?.track_temp_c != null && snapshot?.air_temp_c != null
      ? (snapshot.track_temp_c - snapshot.air_temp_c).toFixed(1)
      : "—";

  const rain = rainBucket(snapshot);

  return (
    <div className="flex flex-col gap-3 h-full">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <MetricCard label="Track Temp" value={trackTemp} unit="°C" trend="neutral" />
        <MetricCard label="Air Temp" value={airTemp} unit="°C" trend="neutral" />
        <MetricCard label="Track − Air" value={delta} unit="°C" trend="neutral" />
        <MetricCard label="Humidity" value={humidity} unit="%" trend="neutral" />
      </div>

      <section className="panel flex-1 p-4 flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <span className="label-caps">Conditions Summary</span>
          <span
            className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded border ${
              rain.alert === "red"
                ? "text-pitwall-accent border-pitwall-accent/50 bg-pitwall-accent/10"
                : rain.alert === "yellow"
                  ? "text-pitwall-yellow border-pitwall-yellow/50 bg-pitwall-yellow/10"
                  : "text-pitwall-green border-pitwall-green/50 bg-pitwall-green/10"
            }`}
          >
            {rain.value}
          </span>
        </div>
        <dl className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-2 text-xs">
          <Row label="Track status">{snapshot?.track_status ?? "—"}</Row>
          <Row label="Active predictor">
            {snapshot?.active_predictor ?? "—"}
          </Row>
          <Row label="Current lap">{snapshot?.current_lap ?? "—"}</Row>
          <Row label="Session ID">{snapshot?.session_id ?? "—"}</Row>
        </dl>
        <p className="text-[11px] text-pitwall-muted leading-relaxed mt-2">
          V1 backend exposes weather as track / air temperature and humidity
          from the FastF1 historical stream. Lap-by-lap rain intensity and
          forecast evolution are <span className="font-mono">V2</span>.
        </p>
      </section>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3 border-b border-pitwall-border/40 py-1">
      <dt className="text-pitwall-muted">{label}</dt>
      <dd className="font-mono text-white">{children}</dd>
    </div>
  );
}
