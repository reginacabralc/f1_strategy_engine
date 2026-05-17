import type { ConnectionStatus } from "../../hooks/useRaceFeed";
import type { PredictorName, RaceSnapshot } from "../../api/types";
import { RaceTable } from "../RaceTable";

interface Props {
  snapshot: RaceSnapshot | null;
  connectionStatus: ConnectionStatus;
  activePredictor?: PredictorName;
}

export function TimingPanel({
  snapshot,
  connectionStatus,
  activePredictor,
}: Props) {
  const drivers = snapshot?.drivers ?? [];
  const inPit = drivers.filter((d) => d.is_in_pit).length;
  const fastest = drivers
    .filter((d) => d.last_lap_ms != null)
    .reduce<typeof drivers[0] | null>(
      (best, d) =>
        !best || (d.last_lap_ms ?? Infinity) < (best.last_lap_ms ?? Infinity)
          ? d
          : best,
      null,
    );

  return (
    <div className="flex flex-col gap-3 h-full min-h-0">
      <div className="grid grid-cols-3 gap-2 shrink-0">
        <StatPill label="Drivers" value={String(drivers.length)} />
        <StatPill label="In Pit" value={String(inPit)} />
        <StatPill
          label="Fastest Last Lap"
          value={
            fastest && fastest.last_lap_ms != null
              ? `${fastest.driver_code} ${(fastest.last_lap_ms / 1000).toFixed(3)}s`
              : "—"
          }
        />
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto">
        <RaceTable
          drivers={drivers}
          isLive={connectionStatus === "open"}
          connectionStatus={connectionStatus}
          activePredictor={activePredictor}
        />
      </div>
    </div>
  );
}

function StatPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="panel px-3 py-2 flex items-center justify-between">
      <span className="label-caps">{label}</span>
      <span className="font-mono text-sm text-white">{value}</span>
    </div>
  );
}
