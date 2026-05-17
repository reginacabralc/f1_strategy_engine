import type { AlertPayload } from "../../api/ws";
import type { RaceSnapshot } from "../../api/types";
import { AlertPanel } from "../AlertPanel";
import { MetricCard } from "../MetricCard";
import { TrackMapPanel } from "../TrackMapPanel";

interface Props {
  snapshot: RaceSnapshot | null;
  alerts: AlertPayload[];
  circuit: string;
  totalLaps?: number;
  isLive: boolean;
}

export function OverviewPanel({
  snapshot,
  alerts,
  circuit,
  totalLaps,
  isLive,
}: Props) {
  const drivers = snapshot?.drivers ?? [];
  const leader = drivers.find((d) => d.position === 1);
  const maxScore = drivers.length
    ? Math.max(...drivers.map((d) => d.undercut_score ?? 0))
    : null;
  const undercutRisk =
    maxScore == null
      ? { value: "—" }
      : maxScore >= 0.7
        ? { value: "HIGH", alert: "red" as const }
        : maxScore >= 0.4
          ? { value: "MEDIUM", alert: "yellow" as const }
          : maxScore > 0
            ? { value: "LOW", alert: "green" as const }
            : { value: "NONE" };

  const trackTemp =
    snapshot?.track_temp_c != null ? snapshot.track_temp_c.toFixed(1) : "—";
  const airTemp =
    snapshot?.air_temp_c != null ? snapshot.air_temp_c.toFixed(1) : "—";

  return (
    <div className="flex flex-col gap-3 h-full min-h-0">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 shrink-0">
        <MetricCard
          label="Current Lap"
          value={String(snapshot?.current_lap ?? "—")}
          unit={totalLaps ? `/ ${totalLaps}` : ""}
          trend="neutral"
        />
        <MetricCard
          label="Leader"
          value={leader?.driver_code ?? "—"}
          trend="neutral"
        />
        <MetricCard label="Track Temp" value={trackTemp} unit="°C" trend="neutral" />
        <MetricCard label="Undercut Risk" {...undercutRisk} />
      </div>

      <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-3 gap-3">
        <div className="lg:col-span-2 min-h-[420px]">
          <TrackMapPanel
            drivers={drivers}
            circuit={circuit}
            currentLap={snapshot?.current_lap}
            totalLaps={totalLaps}
            isLive={isLive}
          />
        </div>
        <div className="flex flex-col gap-3 min-h-0">
          <AlertPanel alerts={alerts} />
          <div className="grid grid-cols-2 gap-2">
            <MetricCard label="Air Temp" value={airTemp} unit="°C" trend="neutral" />
            <MetricCard
              label="Track Status"
              value={snapshot?.track_status ?? "—"}
              trend="neutral"
            />
            <MetricCard
              label="Active Predictor"
              value={snapshot?.active_predictor ?? "—"}
              trend="neutral"
            />
            <MetricCard
              label="Drivers"
              value={String(drivers.length)}
              trend="neutral"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
