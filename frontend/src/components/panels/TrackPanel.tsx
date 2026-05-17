import type { RaceSnapshot } from "../../api/types";
import { TrackMapPanel } from "../TrackMapPanel";

interface Props {
  snapshot: RaceSnapshot | null;
  circuit: string;
  totalLaps?: number;
  isLive: boolean;
}

// Full-bleed track map for the dedicated "Track" tab.
export function TrackPanel({ snapshot, circuit, totalLaps, isLive }: Props) {
  return (
    <div className="h-full min-h-0">
      <TrackMapPanel
        drivers={snapshot?.drivers}
        circuit={circuit}
        currentLap={snapshot?.current_lap}
        totalLaps={totalLaps}
        isLive={isLive}
      />
    </div>
  );
}
